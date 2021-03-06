import pymongo, sys, random
from fish import ProgressFish
depts = open('depts', 'r').read().split("\n")[1:-1]

mconn = pymongo.Connection()
db = mconn.rsparly2012
ms2010 = db.ms2010
ms = db.ms
linkage = db.mpidlinktabledata
election_results = db['2010electionresults']
biodata = db.biodata
postsdata = db.postsdata
voterecordvdm = db.voterecordvdm
vote_types = db.voterecordvotetype
divisions = db.voterecorddivisions
unemployments = db.unemploymentconstituency
crimes = db.crimebyconstituencycrime
expenses = db.expenses_aggregation
coll = db.data
coll.drop()

unemployment_average = map(lambda x: float(x['01/09/2011 00:00:00']), unemployments.find())
unemployment_average = sum(unemployment_average)/len(unemployment_average)

crime_average = map(lambda x: float(x['Total']), crimes.find())
crime_average = sum(crime_average)/len(crime_average)

turnout_average = map(lambda x: float(x['TurnoutPercentage'].strip('%')), election_results.find())
turnout_average = sum(turnout_average)/len(turnout_average)

expense_average = map(lambda x: float(x['Total Claimed']), expenses.find())
expense_average = sum(expense_average)/len(expense_average)

LIMIT = int(1e4)

fish = ProgressFish(total=ms2010.count())
data = ms2010.find({"towhy": "still_in_office"}).limit(LIMIT)
for i, datum in enumerate(data):
    fish.animate(amount=i)
    mp = {}
    
    mp['first_name'] = datum['firstname']
    mp['last_name'] = datum['lastname']
    mp['party'] = datum['party']

    prev_datum = ms.find_one({'constituency': datum['constituency'], 'todate': '2010-04-12'})
    mp_change = prev_datum == None or prev_datum['firstname'] != datum['firstname'] or prev_datum['lastname'] != datum['lastname']
    mp['mp_change'] = mp_change
    mp['party_change'] = prev_datum == None or (not mp_change and prev_datum['party'] != datum['party'])

    mp['election_reason'] = datum['fromwhy'].replace("_", " ").capitalize()

    links = linkage.find_one({'TWFY_Member_id': datum["id"].split("/")[-1]})
    if links == None: continue
    candidate = election_results.find_one({'Parliament_Constituency_id': links['Parliament_Constituency_id'], 'AlphaSurname': datum['lastname']})
    if candidate == None: continue
    mp['region'] = candidate['Region']

    mp['twfy_id'] = links['TWFY_Person_id']

    bio = biodata.find_one({'dods_id': links['DODS_id']})
    gender = bio['gender']
    mp['gender'] = gender

    posts = postsdata.find_one({'dods_id': links['DODS_id']})
    mp['has_government_post'] = posts['has_government_post']
    mp['has_opposition_post'] = posts['has_opposition_post']
    mp['is_sos'] = posts['is_sos']
    mp['is_ssos'] = posts['is_ssos']
    mp['is_mos'] = posts['is_mos']
    mp['is_smos'] = posts['is_smos']
    theirdepts = posts['depts']
    for dept in depts: mp["dept_%s" % dept] = dept in theirdepts

    unemployment = unemployments.find_one({'Parliament_Constituency_id': links['Parliament_Constituency_id']})
    if unemployment == None: continue
    mp['unemployment'] = float(unemployment['01/09/2011 00:00:00']) > unemployment_average

    crime = crimes.find_one({'Constituency': candidate['ConstituencyName']})
    if crime == None: mp['crime'] = random.random() > 0.5
    else: mp['crime'] = float(crime['Total']) > crime_average

    turnout = float(candidate['TurnoutPercentage'].strip("%"))
    mp['turnout'] = turnout > turnout_average

    expense = expenses.find_one({"MP's Name": "%s %s" % (links['FirstName'], links['LastName'])})
    if expense == None: mp['expense'] = random.random() > 0.5
    else: mp['expense'] = float(expense['Total Claimed']) > expense_average

    votes = voterecordvdm.find({'Parliament_People_id':links['Parliament_People_id']})
    for vote in votes:
        division_id = vote['DivisionID']
        vote_type_id = vote['VoteTypeID']
        #vote_type = vote_types.find_one({'VoteTypeID': vote_type_id})['VoteType']
        #division = divisions.find_one({'DivisionID': division_id})['DivTitle']
        mp[division_id] = vote_type_id

    coll.insert(mp)

# Name - MS
# Party - MS
# Gender - bio
# Region - 2010
# MP change - MS
# Party change - MS
# Votes on bills - votes data
# Elected because of (general election)/etc - MS
