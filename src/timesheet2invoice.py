#!/usr/bin/python
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#  
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.

''' Extract data from wrtts2 and output as comma separated file, one line per event.
# Specific for Autodromo at the moment but could be more generic.
# Could also interface with gnucash to get next invoice number.
This creates an invoice using the next invoice number increment.  Once this 
is run the invoice exists in the account file and is hard to remove, it can
however be recycled.  Needs to have python bindings updated.
Run with ~/progs/gnucash-devel/bin/gnucash-env make_timesheet.py X w|m
Where X = period, and is a week or a month, m = month or w = week
'''
''' 
TODO Need to add lots of error trapping 
TODO How to avoid duplicates?  Would need some sort of record file?
TODO Do weekly or monthly reports
TODO If there are no entries, don't create an invoice.
TODO GUI?
'''

import ConfigParser
import sys, os
import MySQLdb
import datetime
import gnucash
import gnucash.gnucash_business
from gnucash import GncNumeric
from gnucash.gnucash_business import Customer, Invoice, Entry

#def cleanAndSave:
#  pass
#  quit()

DATE_OPENED = None # Most likely todays date
try: p_number = (sys.argv[1]) # Specify as number on command line
except: p_number = 3
try: PERIOD = sys.argv[2].lower()
except: PERIOD = "m" # Default to a month

#GnuCash stuff
IGNORE_LOCK = True
CUSTOMER_ID = "000012" # String. Need to specify as timetracker ID != GnuCash ID, could search I guess.
INVOICE_ID = None # String, gncInvoiceNextID from Gnucash
RATE = None # Get from timetracker
PROJECT_ID = 10 # 10 = Company ID in TimeTracker
# To get project IDs "select p_id, p_name from projects;"
CURRENCY = {'GBP':'gbp'}
    
# Read the config file for database access tokens
config_file = "db_conf.cfg" # Keep it secret.  See example file
config = ConfigParser.ConfigParser()
config.read(config_file)
db_user = config.get('database','USER')
db_pass = config.get('database','PASSWD')
db_base = config.get('database','DB')
db_host = config.get('database','DBHOST')  
FILE = config.get('other','FILE')
csv_file =  config.get('other','CSV_FILE')


period = None
#mysql -e "select DATE(al_timestamp) AS date, al_from AS start, TIME(al_duration+al_from) AS finish, al_duration AS duration, al_comment FROM  activity_log WHERE al_activity_id = 24 ORDER BY al_date;" -u mikee wrtts -p
if PERIOD == "m": period = "MONTH"
elif PERIOD == "w": period = "WEEK"

# SQL selects are for Anuko TimeTracker.  Edit as required.
get_data_sql = "select al_date, al_project_id, al_comment, al_duration \
                from activity_log where al_billable = 1 AND al_project_id=10 \
                AND  YEAR (al_date) = 2012 AND " + period + "(al_date) = %s \
                order by al_timestamp;" # month/week supplied on command line

get_rate_sql = "select ub_rate from user_bind WHERE ub_id_p=10"

db = MySQLdb.connect(db_host,db_user,db_pass,db_base)

# prepare a cursor object using cursor() method
cursor = db.cursor()
#cursor = con.cursor(MySQLdb.cursors.DictCursor) # Example dictionary cursor that I should have used.
# execute SQL query using execute() method.
# Fetch a single row using fetchone() method.

cursor.execute(get_rate_sql)
data = cursor.fetchone()
RATE=data[0]

#print type(RATE)
cursor.execute(get_data_sql,(p_number))
if int(cursor.rowcount)== 0: # If there are no entries, don't make an invoice.
  print "\nEmpty report, refusing to create empty invoice.  Quitting.\n\n"
  quit()
data = cursor.fetchall()

# We create a CSV file for two reasons; for import into a spreadsheet, for tracking useage.
csv_filename = csv_file + "-"  + PERIOD + str(p_number) + ".csv" # output filename for csv
# Check if CSV file already exists.  If it does, assume we've run this before and quit
if not os.path.exists(csv_filename):
  csv_file = open(csv_filename,"w")
else: # Crude check if we've run this before.  TODO: Could be improved
  print "\nYou appear to have already run this for this period.\n \
    I will quit now to give you time to think about what you are doing.\n\n" 
  quit()

csv_line="date,task,duration,rate\r\n"
csv_file.write(csv_line)

# For direct to gnucash
session = gnucash.Session("xml://%s" % FILE, IGNORE_LOCK, False, False) ## DANGEROUS if IGNORE LOCK = True  TESTING ONLY!!!!
assert(session != None)
root = session.book.get_root_account()
assert(root != None)
book = session.book
income = root.lookup_by_name("Earned Income")
assert(income != None)
if income.GetType() == -1:
  print "Didn't get income account exiting"
  session.end()
  quit()
assets = root.lookup_by_name("Assets")
recievables = assets.lookup_by_name("Accounts Recievable")
comm_table = book.get_table()
gbp = comm_table.lookup("CURRENCY", "GBP")
customer = book.CustomerLookupByID(CUSTOMER_ID)
assert(customer != None)
assert(isinstance(customer, Customer))

from gnucash.gnucash_core_c import gncInvoiceNextID
iID = gncInvoiceNextID(book.get_instance(),customer.GetEndOwner().get_instance()[1]) 
invoice = Invoice(book, iID, gbp, customer)
assert(invoice != None)
assert(isinstance(invoice, Invoice))
invoice.SetDateOpened(datetime.date.today())



csv_line="date,task,duration,rate\r\n"
csv_file.write(csv_line)
for line in data:
  date = line[0]
  task = line[2]
  duration = str(line[3])
  (h, m, s) = duration.split(':')
  d_duration = float(int(h) * 3600 + int(m) * 60 + int(s))/3600
  #print d_duration
  csv_line=str(date) + "," + task + "," + str(duration) + ","  + str(RATE) + "\r\n"
  csv_file.write(csv_line)
  # Make an entry per invoice line
  entry = gnucash.gnucash_business.Entry(book, invoice)
  entry.SetDateEntered(datetime.date.today())
  entry.SetDate(date)
  entry.SetDescription (task)
  entry.SetInvAccount(income)
  entry.SetAction("Hours")
  entry.SetQuantity(GncNumeric(d_duration*100,100))
  gnc_price = GncNumeric(int(RATE * 100), 100) ## = price x 100 then set denom to 100
  entry.SetInvPrice(gnc_price)
  entry.SetInvTaxIncluded(False)
  
csv_file.close()
session.save() #
session.end()
session.destroy()



