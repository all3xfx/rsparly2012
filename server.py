import cherrypy, pymongo, json, os, itertools
import numpy as np

mconn = pymongo.Connection()
db = mconn.rsparly2012
coll = db.data
divisions = db.voterecorddivisions
vdm = db.voterecordvdm
voterecordvotetype = db.voterecordvotetype

EPSILON = 3

def possible_answers(key): return coll.distinct(key)
def question_text(key):
    labels = {'party': 'What political party are they?',
              'mp_change': 'Have they only been an MP since the last election?',
              'party_change': 'Has their party only been in power since the last election?',
              'election_reason': 'Why were they elected?',
              'region': 'What region is their constituency in?',
              'vvt': 'Estimate the voter turnout when they were last elected',
              'gender': 'What gender are they?'}
    if key in labels: return labels[key]
    else:
        div_title = divisions.find_one({'DivisionID': key})['DivTitle']
        return "How did they vote for %s (%d Labour MPs and %d Conservative MPs voted for this)?" % (div_title.split("-")[0].strip(","), labour_votes(key), tory_votes(key))
        raise "foo"

def answer_texts(key):
    # TODO mp_change, party_change, election_reason, vvt
    if key in ['party', 'region', 'gender', 'election_reason']: answers = possible_answers(key)
    elif key in ['mp_change', 'party_change']: answers = ["Yes", "No"]
    elif key == 'vvt': answers = ["<25%", "25%<=t<50%", "50%<=t<75%", ">=75%"]
    else: answers = map(get_vote_type, possible_answers(key))
    answers.append("Not sure")
    return answers

def parse_answer(key, answer):
    if key in ['party', 'region', 'gender', 'election_reason']: return answer
    elif key in ["mp_change", "party_change"]: return answer == "Yes"
    elif key == 'vvt': {"<25%": 0, "25%<=t<50%": 1, "50%<=t<75%": 2, ">=75%": 3}[key]
    else: return get_vote_id(answer)

def unique(a):
    indices = sorted(range(len(a)), key=a.__getitem__)
    indices = set(next(it) for k, it in itertools.groupby(indices, key=a.__getitem__))
    return [x for i, x in enumerate(a) if i in indices]

def cartesian_product2(arrays):
    la = len(arrays)
    arr = np.empty([len(a) for a in arrays] + [la])
    for i, a in enumerate(np.ix_(*arrays)):
        arr[...,i] = a
    return arr.reshape(-1, la)

def algorithm_u(ns, m):
    def visit(n, a):
        ps = [[] for i in xrange(m)]
        for j in xrange(n):
            ps[a[j + 1]].append(ns[j])
        return ps

    def f(mu, nu, sigma, n, a):
        if mu == 2:
            yield visit(n, a)
        else:
            for v in f(mu - 1, nu - 1, (mu + sigma) % 2, n, a):
                yield v
        if nu == mu + 1:
            a[mu] = mu - 1
            yield visit(n, a)
            while a[nu] > 0:
                a[nu] = a[nu] - 1
                yield visit(n, a)
        elif nu > mu + 1:
            if (mu + sigma) % 2 == 1:
                a[nu - 1] = mu - 1
            else:
                a[mu] = mu - 1
            if (a[nu] + sigma) % 2 == 1:
                for v in b(mu, nu - 1, 0, n, a):
                    yield v
            else:
                for v in f(mu, nu - 1, 0, n, a):
                    yield v
            while a[nu] > 0:
                a[nu] = a[nu] - 1
                if (a[nu] + sigma) % 2 == 1:
                    for v in b(mu, nu - 1, 0, n, a):
                        yield v
                else:
                    for v in f(mu, nu - 1, 0, n, a):
                        yield v

    def b(mu, nu, sigma, n, a):
        if nu == mu + 1:
            while a[nu] < mu - 1:
                visit(n, a)
                a[nu] = a[nu] + 1
            visit(n, a)
            a[mu] = 0
        elif nu > mu + 1:
            if (a[nu] + sigma) % 2 == 1:
                for v in f(mu, nu - 1, 0, n, a):
                    yield v
            else:
                for v in b(mu, nu - 1, 0, n, a):
                    yield v
            while a[nu] < mu - 1:
                a[nu] = a[nu] + 1
                if (a[nu] + sigma) % 2 == 1:
                    for v in f(mu, nu - 1, 0, n, a):
                        yield v
                else:
                    for v in b(mu, nu - 1, 0, n, a):
                        yield v
            if (mu + sigma) % 2 == 1:
                a[nu - 1] = 0
            else:
                a[mu] = 0
        if mu == 2:
            visit(n, a)
        else:
            for v in b(mu - 1, nu - 1, (mu + sigma) % 2, n, a):
                yield v

    n = len(ns)
    a = [0] * (n + 1)
    for j in xrange(1, m + 1):
        a[n - m + j] = j - 1
    return f(m, n, 0, n, a)

def find_result(answers):
    m = len(answers)
    k = 10
    limit = int(1e6)

    best_epsilon_diff = float("inf")
    mps = []

    for i in range(m):
        A = map(dict, list(itertools.islice(itertools.combinations(answers.items(), m-i), limit)))

        P = map(lambda a: list(coll.find(dict(a))), A)
        P = filter(lambda p: len(p) != 0, P)
        if len(P) == 0: continue

        B = sorted(P, key = lambda p: len(p), reverse=True)[0]
        print "%d: %d" % (m-i, len(B))
        epsilon_diff = len(B) - EPSILON
        if epsilon_diff < best_epsilon_diff:
            best_epsilon_diff = epsilon_diff
            mps = B

        if len(B) < EPSILON:
            M = sorted(B, key = lambda b: sum(map(lambda p: b in p, P)), reverse=True)[0]
            return [M, mps]

    print "Epsilon diff: %d" % best_epsilon_diff

    return [[], mps]

# def get_matching_mps(answers): return list(coll.find(dict(answers)))
# def get_cost_answers(mps): return len(mps)

def tory_votes(key): return get_votes(key, 'Conservative')
def labour_votes(key): return get_votes(key, 'Labour')

def get_votes(key, party): return vdm.find({"PARTY_NAME": party, "DivisionID": key, "VoteTypeID": '1'}).count()

def get_vote_type(vote_type): return voterecordvotetype.find_one({'VoteTypeID':vote_type})['VoteType']
def get_vote_id(vote_type): return voterecordvotetype.find_one({'VoteType':vote_type})['VoteTypeID']

def least_covariance(orig_data, cols_to_skip, keys_to_skip):
    modelen = np.bincount(map(len, orig_data)).argmax()
    orig_data = filter(lambda r: len(r) == modelen, orig_data)

    cols_to_skip.extend(['first_name', 'last_name', '_id'])
    cols_to_hash = ['party', 'mp_change', 'party_change', 'election_reason', 'region', 'vvt', 'gender']

    data = map(lambda r: filter(lambda (k, v): k not in cols_to_skip, r.items()), orig_data)
    cols = [[k for k, v in r] for r in data]
    cols = list(set([element for lis in cols for element in lis]))

    hash_maps = {}
    for col in cols:
        if not col in cols_to_hash: continue
        vals = list(set(map(lambda r: r[col], orig_data)))
        mapping = dict(map(lambda r: r[::-1], enumerate(vals)))
        hash_maps[col] = mapping

    data = map(lambda r: map(lambda (k, v): int(hash_maps[k][v]) if k in cols_to_hash else int(v), r), data)
    data = np.transpose(np.array(data))

    covs = np.cov(data)
    covs = np.sum(covs**2, axis=1)
    covs *= 1/covs.max()
    covs = list(covs)

    covs = zip(cols, covs)
    covs = sorted(covs, key = lambda x: x[1], reverse=True)
    covs = filter(lambda r: not r[0] in keys_to_skip, covs)
    return covs[0][0]

def get_response_for_key(key): return {'question': question_text(key), 'question_id': key, 'answers': answer_texts(key)}

class App(object):
    def index(self, **answers):
        keys_to_skip = list(answers)
        for k in answers.keys():
            if answers[k] == "Not sure": del answers[k]
            else: answers[k] = parse_answer(k, answers[k])
        response = {}
        if len(answers) == 0:
            response = get_response_for_key('region')
        elif len(answers) > 25:
            response = {"error": "We failed"}
        else:
            result, mps = find_result(answers)
            if len(result) == 0:
                next_col = least_covariance(mps, map(lambda r: r[0], answers), keys_to_skip)
                response = get_response_for_key(next_col)
            else:
                response = {"success": "%s %s" % (result['first_name'], result['last_name'])}
        return json.dumps(response)
    index.exposed = True

class Root(object): pass
PATH = os.path.abspath(os.path.dirname(__file__))

cherrypy.config.update({'server.socket_port': 8000})
cherrypy.tree.mount(App(), '/api')
cherrypy.tree.mount(Root(), '/', config={
    '/': {
        'tools.staticdir.on': True,
        'tools.staticdir.dir': "%s/client/" % PATH,
        'tools.staticdir.index': 'index.html',
        },
    })
cherrypy.engine.start()
cherrypy.engine.block()
