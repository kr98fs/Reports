# routes.py
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.application import MIMEApplication
from email import encoders
import os.path
from os import path

from flask import session, render_template, flash, redirect, url_for, request, jsonify, json, make_response, after_this_request
#from flask_weasyprint import HTML, render_pdf
import pdfkit


from flask_bootstrap import Bootstrap
from werkzeug.urls import url_parse
from app.models import CourseEnrollee, CourseOffering, ShopName, Member, MemberActivity,\
MonitorSchedule, MonitorScheduleTransaction, MonitorWeekNote, CoordinatorsSchedule,\
ControlVariables, DuesPaidYears, Contact, EmailMessages, Course, CourseOffering, CourseEnrollee
from app import app
from app import db
from sqlalchemy import func, case, desc, extract, select, update, text
from sqlalchemy.exc import SQLAlchemyError, IntegrityError, DBAPIError
from sqlalchemy.orm import aliased
from sqlalchemy.sql import text as SQLQuery

import datetime as dt
from datetime import date, datetime, timedelta

import os.path
from os import path


from flask_mail import Mail, Message
mail=Mail(app)

@app.route('/')
@app.route('/index/')
@app.route('/index', methods=['GET'])
def index():
    shopID = getShopID()
    staffID = getStaffID()

    # GET CURRENT TERM
    term = db.session.query(ControlVariables.Current_Course_Term).filter(ControlVariables.Shop_Number == 1).scalar()
    
    # BUILD ARRAY OF NAMES FOR DROPDOWN LIST OF MEMBERS
    nameArray=[]
    sqlSelect = "SELECT Last_Name, First_Name, Member_ID FROM tblMember_Data "
    sqlSelect += "ORDER BY Last_Name, First_Name "
    nameList = db.engine.execute(sqlSelect)
    position = 0
    for n in nameList:
        position += 1
        lastFirst = n.Last_Name + ', ' + n.First_Name + ' (' + n.Member_ID + ')'
        nameArray.append(lastFirst)
    

    # BUILD COURSE OFFERING ARRAY FOR THE CURRENT TERM
    offeringDict = []
    offeringItems = []

    try:
        sp = "EXEC offerings '" + term + "'"
        sql = SQLQuery(sp)
        offerings = db.engine.execute(sql)
        
    except (SQLAlchemyError, DBAPIError) as e:
        errorMsg = "ERROR retrieving offerings "
        flash(errorMsg,'danger')
        return 'ERROR in offering list build.'
    
    if offerings == None:
        flash('There are no courses offerings for this term.','info')
    else:    
        for offering in offerings:
            # GET CLASS SIZE LIMIT
            capacity = offering.Section_Size
            
            seatsAvailable = capacity - offering.seatsTaken
            if (offering.Section_Closed_Date):
                statusClosed = 'C'
            else:
                statusClosed = ''

            seatsAvailable = capacity - offering.seatsTaken
            if (seatsAvailable > 0):
                statusFull = ''
            else:
                statusFull = 'F'

            fee = offering.courseFee

            if (offering.datesNote == None):
                datesNote = ''
            else:
                datesNote = 'Meets - ' + offering.datesNote

            if (offering.prereq == None):
                prereq = ''
            else:
                prereq = offering.prereq


            offeringItems = {
                'sectionName':offering.courseNumber + '-' + offering.sectionID,
                'term':term,
                'courseNumber':offering.courseNumber,
                'title':offering.title,
                'instructorName':offering.instructorName,
                'dates':offering.Section_Dates,
                'notes':datesNote,
                'capacity':capacity,
                'seatsTaken':offering.seatsTaken,
                'seatsAvailable':seatsAvailable,
                'fee':fee,
                'prereq':prereq,
                'supplies':offering.Section_Supplies,
                'suppliesFee':offering.Section_Supplies_Fee,
            }
            if statusFull != 'F' and statusClosed != 'C':
                offeringDict.append(offeringItems)
   
    # RECENT TRAINING DATES, 30 DAYS OR LESS
    firstWeek = date.today() - timedelta(30)
    firstTrainingDate = firstWeek.strftime('%m-%d-%Y')
    

    # now showing just RA via Last_Monitor_Training;
    # need second dropdown for BW Last_Monitor_Training_Shop_2

    sqlTrainingDates = "SELECT Last_Monitor_Training, format(Last_Monitor_Training,'MMM d, yyyy') AS displayDate "
    sqlTrainingDates += "FROM tblMember_Data "
    sqlTrainingDates += "WHERE Last_Monitor_Training >= '" + firstTrainingDate  + "' "
    sqlTrainingDates += "GROUP BY Last_Monitor_Training "
    sqlTrainingDates += "ORDER BY Last_Monitor_Training"
    
    trainingDates = db.engine.execute(sqlTrainingDates)
   
    return render_template("index.html",nameList=nameArray,offeringDict=offeringDict,trainingDates=trainingDates,shopID=shopID)
   

#PRINT PRESIDENTS REPORT
@app.route("/prtPresidentsReport", methods = ['GET'])
def prtPresidentsReport():
    destination = request.args.get('destination')  # destination is 'PRINT or 'PDF'
    
    # RETRIEVE TODAY'S DATE
    todays_date = date.today()
    todays_dateSTR = todays_date.strftime('%-m-%-d-%Y')

    # COMPUTE VALUES
    curYear = db.session.query(ControlVariables.Current_Dues_Year).filter(ControlVariables.Shop_Number == 1).scalar()
    pastYear = int(curYear) -1
   
    curYrPd = db.session.query(func.count(Member.Member_ID)).filter(Member.Dues_Paid == True).scalar()

    curYrNewMbrs = db.session.query(func.count(Member.Member_ID)).filter(extract('year',Member.Date_Joined)  == curYear).scalar()
    
    mbrsNotCertified = db.session.query(func.count(Member.Member_ID)).filter(Member.Certified != True).filter(Member.Dues_Paid == True).scalar()
   
    curYrInactive = db.session.query(func.count(Member.Member_ID)).filter(extract('year',Member.Inactive_Date)  == curYear).scalar()
    
    pastYrPaid = db.session.query(func.count(DuesPaidYears.Member_ID)).filter(DuesPaidYears.Dues_Year_Paid == pastYear).scalar()
    
    pastYrInactive = db.session.query(func.count(Member.Member_ID)).filter(extract('year',Member.Inactive_Date)  == pastYear).scalar()
    
    
    # SQL QUERY TO COMPUTE THOSE PAID LAST YEAR, NOT PAID THIS YEAR
    sqlCompute = "SELECT tblDues_Paid_Years.Member_ID, tblDues_Paid_Years.Dues_Year_Paid "
    sqlCompute += "FROM tblDues_Paid_Years "
    sqlCompute += "WHERE (((tblDues_Paid_Years.Member_ID) Not In "
    sqlCompute += "(Select Member_ID from tblDues_Paid_Years where Dues_Year_Paid = '" + str(pastYear) + "')) "
    sqlCompute += "AND ((tblDues_Paid_Years.Dues_Year_Paid)='" + curYear + "'))"
    records = db.engine.execute(sqlCompute)
    pdPastNotCur = 0
    for r in records:
        pdPastNotCur += 1

    pastYrNewMbrs = db.session.query(func.count(Member.Member_ID)).filter(extract('year',Member.Date_Joined)  == pastYear).scalar()
    
    volunteers = db.session.query(func.count(Member.Member_ID)).filter(Member.NonMember_Volunteer == True).scalar()

    recordsInDB = db.session.query(func.count(Member.Member_ID)).scalar()
    
    return render_template("rptPresident.html",todaysDate=todays_dateSTR,curYear=curYear,pastYear=pastYear,\
    curYrPd=curYrPd,curYrNewMbrs=curYrNewMbrs,mbrsNotCertified=mbrsNotCertified,curYrInactive=curYrInactive,\
    pastYrPaid=pastYrPaid,pastYrInactive=pastYrInactive,pdPastNotCur=pdPastNotCur,pastYrNewMbrs=pastYrNewMbrs,\
    volunteers=volunteers,recordsInDB=recordsInDB)
            
 
@app.route("/prtMentors", methods=["GET"])
def prtMentorsTable():
    destination = request.args.get('destination')
    todays_date = date.today()
    todays_dateSTR = todays_date.strftime('%-m-%-d-%Y')
         
    mentors = db.session.query(Member)\
        .filter(Member.Mentor == True)\
        .order_by(Member.Last_Name,Member.First_Name)\
        .all()
    mentorDict = []
    mentorItem = []
    recordCnt = 0
    for m in mentors:
        displayName = m.Last_Name + ', ' + m.First_Name 
        if m.Nickname != None:
            displayName += ' (' + m.Nickname + ')'
        
        if m.Cell_Phone == None:
            cellPhone = ''
        else:
            cellPhone = m.Cell_Phone
        
        if m.Home_Phone == None:
            homePhone = ''
        else:
            homePhone = m.Home_Phone

        mentorItem = {
            'name':displayName,
            'cellPhone':cellPhone,
            'homePhone':homePhone,
            'eMail':m.eMail
        }
        mentorDict.append(mentorItem)
        recordCnt += 1
    return render_template("rptMentors.html",todaysDate=todays_dateSTR,mentorDict=mentorDict,recordCnt=recordCnt)

@app.route("/prtContacts", methods=["GET"])
def prtContacts():
    destination = request.args.get('destination')
    todays_date = date.today()
    todays_dateSTR = todays_date.strftime('%-m-%-d-%Y')
          
    # GET LIST OF CONTACT GROUPS
    groups = db.session.query(func.count(Contact.Contact_Group).label('count'),Contact.Contact_Group).group_by(Contact.Contact_Group).all()
    # for g in groups:
    #     print (g.Contact_Group,g.count)


    sqlContacts = "SELECT Contact_Group, Position, "
    sqlContacts += "tblContact_List.Member_ID as MemberID, [Last_Name], [First_Name],[Middle_Name],Nickname, "
    sqlContacts += "eMail, Home_Phone, Cell_Phone, Expires "
    sqlContacts += "FROM tblContact_List "
    sqlContacts += "LEFT JOIN tblMember_Data ON tblContact_List.Member_ID = tblMember_Data.Member_ID "
    sqlContacts += "ORDER BY Contact_Group, Position, Last_Name, First_Name"

    contacts = db.engine.execute(sqlContacts)
   
    contactDict = []
    contactItem = []
    for c in contacts:
        contactGroup = c.Contact_Group
        position = c.Position
        if c.Last_Name == None or c.First_Name == None:
            displayName = ''
        else:
            displayName = c.Last_Name + ', ' + c.First_Name 
            if c.Nickname != None:
                displayName += ' (' + c.Nickname + ')'
            
        if c.Cell_Phone == None:
            cellPhone = ''
        else:
            cellPhone = c.Cell_Phone
        
        if c.Home_Phone == None:
            homePhone = ''
        else:
            homePhone = c.Home_Phone

        contactItem = {
            'contactGroup':contactGroup,
            'position':position,
            'name':displayName,
            'cellPhone':cellPhone,
            'homePhone':homePhone,
            'eMail':c.eMail
        }
        contactDict.append(contactItem)
    return render_template("rptContactList.html",todaysDate=todays_dateSTR,contactDict=contactDict,groups=groups)
 
           

#PRINT WEEKLY LIST OF CONTACTS FOR COORDINATOR
# @app.route("/printWeeklyMonitorContacts", methods=['GET'])
# def printWeeklyMonitorContacts():
#     dateScheduled=request.args.get('date')
#     shopNumber=request.args.get('shop')
#     destination = request.args.get('destination')

#     # GET LOCATION NAME FOR REPORT HEADING
#     shopRecord = db.session.query(ShopName).filter(ShopName.Shop_Number==shopNumber).first()
#     shopName = shopRecord.Shop_Name
    
#     #  DETERMINE START OF WEEK DATE
#     #  CONVERT TO DATE TYPE
#     dateScheduledDat = datetime.strptime(dateScheduled,'%Y-%m-%d')
#     dayOfWeek = dateScheduledDat.weekday()

#     # GET BEGIN, END DATES FOR REPORT HEADING
#     beginDateDAT = dateScheduledDat 
#     beginDateSTR = beginDateDAT.strftime('%m-%d-%Y')

#     endDateDAT = beginDateDAT + timedelta(days=6)
#     endDateSTR = endDateDAT.strftime('%m-%d-%Y')

#     weekOfHdg = beginDateDAT.strftime('%B %d, %Y')
    
#     # RETRIEVE SCHEDULE FOR SPECIFIC WEEK
#     todays_date = date.today()
#     todays_dateSTR = todays_date.strftime('%-m-%-d-%Y')

#     # VARIABLES FOR DUPLICATE NAME CHECK
#     savedSMname=''
#     savedTCname=''
    
#     # BUILD SELECT STATEMENT TO RETRIEVE SM MEMBERS SCHEDULE FOR CURRENT YEAR FORWARD
#     sqlSelectSM = "SELECT tblMember_Data.Member_ID as memberID, "
#     sqlSelectSM += "First_Name + ' ' + Last_Name as displayName, "
#     sqlSelectSM += "Last_Monitor_Training as trainingDate, DATEPART(year,Last_Monitor_Training) as trainingYear, "
#     sqlSelectSM += "'N' as trainingNeeded,"
#     sqlSelectSM += " format(Date_Scheduled,'M/d/yyyy') as DateScheduled, DATEPART(year,Date_Scheduled) as scheduleYear, "
#     sqlSelectSM += "Duty, eMail, Home_Phone, Cell_Phone,tblMember_Data.Monitor_Duty_Waiver_Expiration_Date as waiver "
#     sqlSelectSM += "FROM tblMember_Data "
#     sqlSelectSM += "LEFT JOIN tblMonitor_Schedule ON tblMonitor_Schedule.Member_ID = tblMember_Data.Member_ID "
#     sqlSelectSM += "WHERE Date_Scheduled between '" + beginDateSTR + "' and '" + endDateSTR + "' "
#     sqlSelectSM += " and (tblMonitor_Schedule.Duty = 'Shop Monitor' or tblMonitor_Schedule.Duty = 'Tool Crib') "
#     sqlSelectSM += " and tblMonitor_Schedule.Shop_Number = " + shopNumber 
#     sqlSelectSM += "ORDER BY Duty, Last_Name, First_Name"
#     monitors = db.engine.execute(sqlSelectSM)
    
#     SMmonitors = []
#     TCmonitors = []

#     # STEP THROUGH RESULT SET, DETERMINE IF TRAINING IS NEEDED, BUILD 2D ARRAY (LIST WITHIN LIST)
#     for m in monitors:
#         # IS TRAINING NEEDED?
#         if (m.waiver == None):  # if no waiver 
#             if (m.trainingYear == None):  # if last training year is blank
#                 needsTraining = 'Y'
#             else:
#                 intTrainingYear = int(m.trainingYear) +2  # int of last training year
#                 intScheduleYear = int(m.scheduleYear) # int of schedule year
#                 if (intTrainingYear <= intScheduleYear):
#                     needsTraining = 'Y'
#                 else:
#                     needsTraining = 'N'
#         else:
#             needsTraining = 'N'

#         #   BUILD SHOP MONITOR ARRAYS
#         #   PUT DATA INTO ROW OF ARRAY (SMnames or TCnames)

#         #   Group - Shop Monitor; 
#         if (m.Duty == 'Shop Monitor' and m.displayName != savedSMname):  # ELIMINATE DUPLICATE NAMES
#             savedSMname = m.displayName
#             SMmonitor = {'name':m.displayName,
#                 'trainingYear': m.trainingYear,
#                 'eMail': m.eMail,
#                 'homePhone':m.Home_Phone,
#                 'cellPhone':m.Cell_Phone,
#                 'needsTraining':needsTraining}
#             if SMmonitor['trainingYear'] == None:
#                 SMmonitor['trainingYear'] = ''
#             if SMmonitor['homePhone'] == None:
#                 SMmonitor['homePhone'] = ''
#             if SMmonitor['cellPhone'] == None:
#                 SMmonitor['cellPhone'] = ''
#             SMmonitors.append(SMmonitor)

#         #   Group - Tool Crib;  
#         if (m.Duty == 'Tool Crib' and m.displayName != savedTCname):    # ELIMINATE DUPLICATE NAMES
#             savedTCname = m.displayName 
#             TCmonitor = {'name':m.displayName,
#                 'trainingYear': m.trainingYear,
#                 'eMail': m.eMail,
#                 'homePhone':m.Home_Phone,
#                 'cellPhone':m.Cell_Phone,
#                 'needsTraining':needsTraining}
#             if TCmonitor['trainingYear'] == None:
#                 TCmonitor['trainingYear'] = ''
#             if TCmonitor['homePhone'] == None:
#                 TCmonitor['homePhone'] = ''
#             if TCmonitor['cellPhone'] == None:
#                 TCmonitor['cellPhone'] = ''
#             TCmonitors.append(TCmonitor)
            
    
#     if (destination == 'PDF'):
#         #html =  render_template("rptWeeklyMonitorSchedule.h
#         html = render_template("rptWeeklyContacts.html",\
#             beginDate=beginDateSTR,endDate=endDateSTR,todaysDate=todays_dateSTR,\
#             locationName=shopName,\
#             SMmonitors=SMmonitors,TCmonitors=TCmonitors
#             )
#         # DEFINE PATH TO USE TO STORE PDF
#         currentWorkingDirectory = os.getcwd()
#         pdfDirectoryPath = currentWorkingDirectory + "/app/static/pdf"
#         filePath = pdfDirectoryPath + "/rptWeeklyContacts.pdf"
#         options = { 
#             "enable-local-file-access": None
#         }
#         #pdfkit.from_string(html,filePath, options=options)
#         return redirect(url_for('index'))
#     else:
#         return render_template("rptWeeklyContacts.html",\
#             beginDate=beginDateSTR,endDate=endDateSTR,todaysDate=todays_dateSTR,\
#             locationName=shopName,\
#             SMmonitors=SMmonitors,TCmonitors=TCmonitors
#             )
    
    
#PRINT MEMBER MONITOR SCHEDULE TRANSACTIONS AND NOTES
@app.route("/prtMonitorTransactions", methods=["GET"])
def prtMonitorTransactions():
    memberID=request.args.get('memberID')
    destination = request.args.get('destination')
    curYear = request.args.get('year')
    lastYear = int(curYear)-1

    # GET TODAYS DATE
    todays_date = date.today()
    #todaysDate = todays_date.strftime('%-m-%-d-%Y')
    displayDate = todays_date.strftime('%B %-d, %Y') 

    # GET MEMBER NAME
    member = db.session.query(Member).filter(Member.Member_ID == memberID).first()
    displayName = member.First_Name
    if (member.Nickname != None and member.Nickname != ''):
        displayName += ' (' + member.Nickname + ')'
    displayName += ' ' + member.Last_Name

    # GET MONITOR SCHEDULE TRANSACTIONS
    transactions = db.session.query(MonitorScheduleTransaction)\
    .filter(MonitorScheduleTransaction.Member_ID == memberID)\
    .all()
    # .filter(MonitorScheduleTransaction.Date_Scheduled.year == curYear)\
    
    transactionDict = []
    transactionItem = []
    for t in transactions:
        if (str(t.Date_Scheduled.year) == curYear):
            transDateTime = t.Transaction_Date.strftime('%m-%d-%Y %I:%M %p')
            transType = t.Transaction_Type
            scheduled = t.Date_Scheduled.strftime('%m-%d-%Y')
            shift = t.AM_PM
            duty = t.Duty
            staffID = t.Staff_ID
            staffInitials = db.session.query(Member.Initials).filter(Member.Member_ID == staffID).scalar()
            if staffInitials == None:
                staffInitials=''
            
            transactionItem = {
                'transDateTime':transDateTime,
                'transType':transType,
                'scheduledDate':scheduled,
                'shift':shift,
                'duty':duty,
                'staffInitials':staffInitials
            }
            transactionDict.append(transactionItem) 


    # BUILD SELECT STATEMENT TO RETRIEVE NOTES FOR SPECIFIED MEMBER
    notes = db.session.query(MonitorWeekNote)\
    .all()
    #.filter(MonitorWeekNote.Date_Of_Change.year == curYear or MonitorWeekNote.Date_Of_Change == pastYear)\
    if notes == None:
        flash("There are no notes for this member.")
    notesDict = []
    notesItem = []
    for n in notes:
        note = str(n.Schedule_Note)    
        if note.find(memberID) != -1\
        and (n.Date_Of_Change.year == curYear or n.Date_Of_Change.year == lastYear):
            initials = db.session.query(Member.Initials).filter(Member.Member_ID == n.Author_ID).scalar()
            
            notesItem = {
                'noteDateTime':n.Date_Of_Change.strftime('%m-%d-%Y %I:%M %p'),
                'noteText':n.Schedule_Note,
                'staffInitials':initials
            }
            notesDict.append(notesItem) 


    if (destination == 'PDF') : 
        html =  render_template("rptWeeklyNotes.html",\
            #beginDate=beginDateSTR,endDate=endDateSTR,\
            #locationName=shopName,notes=notes,weekOfHdg=weekOfHdg,\
            todaysDate=displayDate
            )
        currentWorkingDirectory = os.getcwd()
        pdfDirectoryPath = currentWorkingDirectory + "/app/static/pdf"
        filePath = pdfDirectoryPath + "/rptWeeklyNotes.pdf"    
        options = {"enable-local-file-access": None}
        #pdfkit.from_string(html,filePath, options=options)
        return redirect(url_for('index'))
    else:
        return render_template("rptMonitorTransactions.html",\
            transactionDict=transactionDict,\
            notesDict=notesDict,displayName=displayName,\
            displayDate=displayDate,memberID=memberID)

# PRINT MEMBER MONITOR DUTY SCHEDULE       
@app.route ("/prtMemberSchedule")
def prtMemberSchedule():
    memberID=request.args.get('memberID')
    # GET MEMBER NAME
    member = db.session.query(Member).filter(Member.Member_ID== memberID).first()
    displayName = member.First_Name + ' ' + member.Last_Name
    lastTrainingRA = member.Last_Monitor_Training
    lastTrainingBW = member.Last_Monitor_Training_Shop_2

    # RETRIEVE LAST_ACCEPTABLE_TRAINING_DATE FROM tblControl_Variables
    lastAcceptableTrainingDate = db.session.query(ControlVariables.Last_Acceptable_Monitor_Training_Date).filter(ControlVariables.Shop_Number == '1').scalar()
    if lastTrainingRA == None:
        needsTrainingRA = 'Y'
    else:
        if (lastTrainingRA < lastAcceptableTrainingDate):
            needsTrainingRA = 'Y'
        else:
            needsTrainingRA = 'N'
    if lastTrainingBW == None:
        needsTrainingBW = 'Y'
    else:
        if (lastTrainingBW < lastAcceptableTrainingDate):
            needsTrainingBW = 'Y'
        else:
            needsTrainingBW = 'N'


    # RETRIEVE MEMBER SCHEDULE FOR CURRENT YEAR AND FORWARD
    #est = timezone('America/New_York')
    todays_date = date.today()
    currentYear = todays_date.year
    beginDateDAT = datetime(todays_date.year,1,1)
    todays_dateSTR = todays_date.strftime('%m-%d-%Y')
    beginDateSTR = beginDateDAT.strftime('%m-%d-%Y')
    if lastTrainingRA != None:
        lastTrainingRAstr = lastTrainingRA.strftime('%m-%d-%Y')
    else:
        lastTrainingRAstr = ''
    if lastTrainingBW != None:
        lastTrainingBWstr = lastTrainingBW.strftime('%m-%d-%Y')
    else:
        lastTrainingBWstr = ''
        
    # BUILD SELECT STATEMENT TO RETRIEVE MEMBERS SCHEDULE FOR CURRENT YEAR FORWARD
    sqlSelect = "SELECT tblMember_Data.Member_ID as memberID, "
    sqlSelect += "First_Name + ' ' + Last_Name as displayName, tblShop_Names.Shop_Name, "
    sqlSelect += "Last_Monitor_Training as trainingDate, tblMonitor_Schedule.Member_ID, "
    sqlSelect += " format(Date_Scheduled,'MMM d, yyyy') as DateScheduled, AM_PM, Duty, No_Show, tblMonitor_Schedule.Shop_Number "
    sqlSelect += "FROM tblMember_Data "
    sqlSelect += "LEFT JOIN tblMonitor_Schedule ON tblMonitor_Schedule.Member_ID = tblMember_Data.Member_ID "
    sqlSelect += "LEFT JOIN tblShop_Names ON tblMonitor_Schedule.Shop_Number = tblShop_Names.Shop_Number "
    sqlSelect += "WHERE tblMember_Data.Member_ID = '" + memberID + "' and Date_Scheduled >= '"
    sqlSelect += beginDateSTR + "' ORDER BY Date_Scheduled desc, AM_PM, Duty"

    schedule = db.engine.execute(sqlSelect)
    
    return render_template("rptMemberSchedule.html",displayName=displayName,\
    lastTrainingRA=lastTrainingRAstr, needsTrainingRA=needsTrainingRA,\
    lastTrainingBW=lastTrainingBWstr, needsTrainingBW=needsTrainingBW,\
    schedule=schedule,todays_date=todays_dateSTR)



@app.route("/eMailCoordinator", methods=["GET","POST"])
def eMailCoordinator():
    # THIS ROUTINE ONLY RETURNS THE EMAIL MESSAGE TO BE USED FOR COORDINATORS ONLY EMAILS
    # ___________________________________________________________________________________

   # LOOK UP MESSAGE TO BE USED FOR EMAILS TO COORDINATORS
    sqlEmailMsgs = "SELECT [Email Name] as eMailMsgName, [Email Message] as eMailMessage FROM tblEmail_Messages "
    sqlEmailMsgs += "WHERE [Email Name] = 'Email To Coordinators'"
    eMailMessages = db.engine.execute(sqlEmailMsgs)
    eMailMsg = ''
    for e in eMailMessages:
        eMailMsg=e.eMailMessage

    return jsonify(eMailMsg=eMailMsg)

@app.route("/eMailCoordinatorAndMonitors", methods=["GET","POST"])
def eMailCoordinatorAndMonitors():
    # GET WEEKOF DATE
    weekOf = request.args.get('weekOf')
    shopNumber = request.args.get('shopNumber')

    weekOfDAT = datetime.strptime(weekOf,'%Y-%m-%d')
    beginDateDAT = weekOfDAT
    beginDateSTR = beginDateDAT.strftime('%m-%d-%Y')
    endDateDAT = beginDateDAT + timedelta(days=6)
    endDateSTR = endDateDAT.strftime('%m-%d-%Y')

    # RETURN COORDINBATOR AND MONITORS NAMES AND EMAIL ADDRESSES; COORDINATORS PHONE
    # BUILD SELECT STATEMENT TO RETRIEVE SM MEMBERS SCHEDULE FOR CURRENT YEAR FORWARD
    sqlMonitors = "SELECT tblMember_Data.Member_ID as memberID, "
    sqlMonitors += "First_Name + ' ' + Last_Name as displayName, eMail "
    sqlMonitors += "FROM tblMember_Data "
    sqlMonitors += "LEFT JOIN tblMonitor_Schedule ON tblMonitor_Schedule.Member_ID = tblMember_Data.Member_ID "
    sqlMonitors += "WHERE Date_Scheduled between '" + beginDateSTR + "' and '" + endDateSTR + "' "
    sqlMonitors += "ORDER BY Last_Name, First_Name"
   
    monitors = db.engine.execute(sqlMonitors)
    monitorDict = []
    monitorItem = []
    savedName = ''
    
    for m in monitors:
        monitorItem = {
            'name':m.displayName,
            'eMail': m.eMail} 
        
        if savedName != m.displayName :
            monitorDict.append(monitorItem)
        savedName = m.displayName

    # LOOK UP EMAIL MESSAGE FOR COORDINATOR
    sqlEmailMsgs = "SELECT [Email Name] as eMailMsgName, [Email Message] as eMailMessage FROM tblEmail_Messages "
    sqlEmailMsgs += "WHERE [Email Name] = 'Email To Coordinators'"
    eMailMessages = db.engine.execute(sqlEmailMsgs)
    eMailMsg=''
    for e in eMailMessages:
        eMailMsg=e.eMailMessage

    return jsonify(monitorDict=monitorDict,eMailMsg=eMailMsg)

@app.route("/getMembersEmailAddress", methods=["GET","POST"])
def getMembersEmailAddress():
    memberID=request.args.get('memberID')
    weekOf = request.args.get('weekOf')
    shopNumber = request.args.get('shopNumber')
    weekOfDat = datetime.strptime(weekOf,'%Y-%m-%d')
    displayDate = weekOfDat.strftime('%B %d, %Y') 

    # GET MEMBER'S EMAIL ADDRESS;
    eMail=db.session.query(Member.eMail).filter(Member.Member_ID == memberID).scalar()

    # LOOK UP EMAIL MESSAGE FOR MEMBER
    eMailMsg=db.session.query(EmailMessages.eMailMessage).filter(EmailMessages.eMailMsgName == 'Email To Members').scalar()
    
    return jsonify(eMail=eMail,eMailMsg=eMailMsg,curWeekDisplayDate=displayDate)


# THE FOLLOWING ROUTINE IS CALLED WHEN THE USER SELECTS A WEEK
@app.route("/getCoordinatorData", methods=["GET","POST"])
def getCoordinatorData():
    # GET WEEKOF DATE
    # RETURN COORDINATOR NAME, EMAIL, PHONE
    weekOf = request.args.get('weekOf')
    shopNumber = request.args.get('shopNumber')
    weekOfDat = datetime.strptime(weekOf,'%Y-%m-%d')
    displayDate = weekOfDat.strftime('%B %d, %Y')  #'%m/%d/%Y')

    # GET COORDINATOR ID FROM COORDINATOR TABLE
    coordinatorRecord = db.session.query(CoordinatorsSchedule)\
        .filter(CoordinatorsSchedule.Start_Date==weekOf)\
        .filter(CoordinatorsSchedule.Shop_Number==shopNumber).first()
    if coordinatorRecord == None:
        coordID= ''
        coordName = 'Not assigned.'
        coordEmail = ''
        coordPhone = ''
    else:
        # LOOK UP COORDINATORS NAME
        coordinatorID = coordinatorRecord.Coordinator_ID
        memberRecord = db.session.query(Member).filter(Member.Member_ID==coordinatorID).first()
        if memberRecord == None:
            coordID = ''
            coordName = 'Not assigned.'
            coordEmail = ''
            coordPhone = ''
        else:
            coordID = memberRecord.Member_ID
            coordName = memberRecord.First_Name + ' ' + memberRecord.Last_Name
            coordEmail = memberRecord.eMail
            coordPhone = memberRecord.Cell_Phone

    return jsonify(
        coordID=coordID,
        coordName=coordName,
        coordEmail=coordEmail,
        coordPhone=coordPhone,
        curWeekDisplayDate=displayDate
    )

@app.route("/sendEmail", methods=["GET","POST"])
def sendEmail():
    # DETERMINE PATH TO PDF FILES
    currentWorkingDirectory = os.getcwd()
    pdfDirectoryPath = currentWorkingDirectory + "/app/static/pdf"
    filePath = pdfDirectoryPath + "/printWeeklyMonitorSchedule.pdf"
   
    # GET RECIPIENT
    recipient = request.args.get('recipient')
    bcc=("Woodshop","villagesWoodShop@embarqmail.com")
    #cc=("Richard l. Hartley","hartl1r@gmail.com")
    # FOR TESTING PURPOSES ..............................
    recipient = ("Richard Hartley", "hartl1r@gmail.com")

    recipientList = []
    recipientList.append(recipient)
    subject = request.args.get('subject')
    message = request.args.get('message')
    msg = Message('Hello', sender = 'hartl1r@gmail.com', recipients = recipientList) #, bcc=bcc)
    msg.subject = subject
    msg.body = message

    # ADD ATTACHMENTS

    # DETERMINE PATH TO PDF FILES
    currentWorkingDirectory = os.getcwd()
    pdfDirectoryPath = currentWorkingDirectory + "/app/static/pdf"
    
    # CHECK FOR A SCHEDULE REPORT
    filePath = pdfDirectoryPath + "/rptWeeklyMonitorSchedule.pdf"
    if (path.exists(filePath)):
        with app.open_resource(filePath) as fp:
            msg.attach(filename="rptSchedule.pdf",disposition="attachment",content_type="application/pdf",data=fp.read())

    # CHECK FOR A CONTACTS REPORT
    filePath = pdfDirectoryPath + "/rptWeeklyContacts.pdf"
    if (path.exists(filePath)):
        with app.open_resource(filePath) as fp:
            msg.attach(filename="rptContacts.pdf",disposition="attachment",content_type="application/pdf",data=fp.read())

    # CHECK FOR A NOTES REPORT
    filePath = pdfDirectoryPath + "/rptWeeklyNotes.pdf"
    if (path.exists(filePath)):
        with app.open_resource(filePath) as fp:
            msg.attach(filename="rptNotes.pdf",disposition="attachment", content_type ="application/pdf",data=fp.read())

    # CHECK FOR A SUB LIST REPORT
    filePath = pdfDirectoryPath + "/rptSubList.pdf"
    if (path.exists(filePath)):  
        with app.open_resource(filePath) as fp:
            msg.attach(filename="rptSubList.pdf",disposition="attachment",content_type="application/pdf",data=fp.read())

    
    # SEND THE EMAIL
    mail.send(msg)
    RemovePDFfiles(pdfDirectoryPath)
    #flash ('Message sent.','SUCCESS')
    return redirect(url_for('index'))


def RemovePDFfiles(pdfDirectoryPath):
    # REMOVE PDF FILES
    
    filePath = pdfDirectoryPath + "/rptWeeklyMonitorSchedule.pdf"
    if (os.path.exists(filePath)):
        os.remove(filePath)
    
    filePath = pdfDirectoryPath + "/rptWeeklyContacts.pdf"
    if (os.path.exists(filePath)):
        os.remove(filePath)

    filePath = pdfDirectoryPath + "/rptWeeklyNotes.pdf"
    if (os.path.exists(filePath)):
        os.remove(filePath)

    filePath = pdfDirectoryPath + "/rptSubList.pdf"
    if (os.path.exists(filePath)):
        os.remove(filePath)

def TrainingNeeded(lastTrainingDate): 
    todays_date = date.today()
    todays_dateSTR = todays_date.strftime('%-m-%-d-%Y')
    thisYear = todays_date.strftime("%Y")
    lastAcceptableTrainingYear = int(thisYear) - 2
    
    if lastTrainingDate == None:
        return True
    
    try:
        lastTrainingYear = lastTrainingDate.strftime("%Y")
        if int(lastTrainingYear) <= lastAcceptableTrainingYear:
            return True
        else:
            return False
    except:
        print ('Error in TrainingNeeded routine using - ', lastTrainingDate)
        return True

@app.route("/prtAllClasses", methods=["GET"])
def prtAllClasses():
    destination = request.args.get('destination')
    todays_date = date.today()
    displayDate = todays_date.strftime('%-B %d, %Y')
    term = db.session.query(ControlVariables.Current_Course_Term).filter(ControlVariables.Shop_Number == 1).scalar()
    
    # BUILD COURSE OFFERING ARRAY FOR THE CURRENT TERM
    offeringDict = []
    offeringItems = []

    try:
        sp = "EXEC offerings '" + term + "'"
        sql = SQLQuery(sp)
        offerings = db.engine.execute(sql)
        
    except (SQLAlchemyError, DBAPIError) as e:
        errorMsg = "ERROR retrieving offerings "
        flash(errorMsg,'danger')
        return 'ERROR in offering list build.'
    
    if offerings == None:
        flash('There are no courses offerings for this term.','info')
    else:    
        for offering in offerings:
            # GET CLASS SIZE LIMIT
            capacity = offering.Section_Size
            
            seatsAvailable = capacity - offering.seatsTaken
           
            if offering.Section_Closed_Date == None:
                statusClosed = ''
            else:
                if (offering.Section_Closed_Date.date() <= todays_date):
                    statusClosed = 'C'
                else:
                    statusClosed = ' '

            seatsAvailable = capacity - offering.seatsTaken
            if (seatsAvailable > 0):
                statusFull = ''
            else:
                statusFull = 'F'

            fee = offering.courseFee

            if (offering.datesNote == None):
                datesNote = ''
            else:
                datesNote = 'Meets - ' + offering.datesNote

            if (offering.prereq == None):
                prereq = ''
            else:
                prereq = offering.prereq


            offeringItems = {
                'sectionName':offering.courseNumber + '-' + offering.sectionID,
                'term':term,
                'courseNumber':offering.courseNumber,
                'title':offering.title,
                'instructorName':offering.instructorName,
                'dates':offering.Section_Dates,
                'notes':datesNote,
                'capacity':capacity,
                'seatsTaken':offering.seatsTaken,
                'seatsAvailable':seatsAvailable,
                'fee':fee,
                'prereq':prereq,
                'supplies':offering.Section_Supplies,
                'suppliesFee':offering.Section_Supplies_Fee,
                'fullMsg':statusFull,
                'closedMsg':statusClosed
            }
            offeringDict.append(offeringItems)
            
    return render_template("rptAllClasses.html",offeringDict=offeringDict,term=term,displayDate=displayDate)

@app.route("/prtOpenClasses", methods=["GET"])
def prtOpenClasses():
    destination = request.args.get('destination')
    todays_date = datetime.today()
    displayDate = todays_date.strftime('%-B %d, %Y')
    term = db.session.query(ControlVariables.Current_Course_Term).filter(ControlVariables.Shop_Number == 1).scalar()

    # BUILD COURSE OFFERING ARRAY FOR THE CURRENT TERM
    offeringDict = []
    offeringItems = []

    try:
        sp = "EXEC offerings '" + term + "'"
        sql = SQLQuery(sp)
        offerings = db.engine.execute(sql)
        
    except (SQLAlchemyError, DBAPIError) as e:
        errorMsg = "ERROR retrieving offerings "
        flash(errorMsg,'danger')
        return 'ERROR in offering list build.'
    
    if offerings == None:
        flash('There are no courses offerings for this term.','info')
    else:    
        for offering in offerings:
            # GET CLASS SIZE LIMIT
            capacity = offering.Section_Size
            
            seatsAvailable = capacity - offering.seatsTaken
            if (offering.Section_Closed_Date == None):
                statusClosed=''
            else:
                if (todays_date >= offering.Section_Closed_Date):
                    statusClosed = 'C'
                else:
                    statusClosed = ''

            seatsAvailable = capacity - offering.seatsTaken
            if (seatsAvailable > 0):
                statusFull = ''
            else:
                statusFull = 'F'

            fee = offering.courseFee

            if (offering.datesNote == None):
                datesNote = ''
            else:
                datesNote = 'Meets - ' + offering.datesNote

            if (offering.prereq == None):
                prereq = ''
            else:
                prereq = offering.prereq


            offeringItems = {
                'sectionName':offering.courseNumber + '-' + offering.sectionID,
                'term':term,
                'courseNumber':offering.courseNumber,
                'title':offering.title,
                'instructorName':offering.instructorName,
                'dates':offering.Section_Dates,
                'notes':datesNote,
                'capacity':capacity,
                'seatsTaken':offering.seatsTaken,
                'seatsAvailable':seatsAvailable,
                'fee':fee,
                'prereq':prereq,
                'supplies':offering.Section_Supplies,
                'suppliesFee':offering.Section_Supplies_Fee,
            }

            if statusFull != 'F' and statusClosed != 'C':
                offeringDict.append(offeringItems)
            
    return render_template("rptOpenClasses.html",offeringDict=offeringDict,term=term,displayDate=displayDate)


@app.route("/ClassLists", methods=["GET"])
def ClassLists():
    destination = request.args.get('destination')
    todays_date = datetime.today()
    displayDate = todays_date.strftime('%-B %d, %Y')
    term = db.session.query(ControlVariables.Current_Course_Term).filter(ControlVariables.Shop_Number == 1).scalar()

    # BUILD COURSE OFFERING ARRAY FOR THE CURRENT TERM
    offeringDict = []
    offeringItems = []

    try:
        sp = "EXEC offerings '" + term + "'"
        sql = SQLQuery(sp)
        offerings = db.engine.execute(sql)
        
    except (SQLAlchemyError, DBAPIError) as e:
        errorMsg = "ERROR retrieving offerings "
        flash(errorMsg,'danger')
        return 'ERROR in offering list build.'
    
    if offerings == None:
        flash('There are no courses offerings for this term.','info')
    else:    
        for offering in offerings:
            # GET CLASS SIZE LIMIT
            capacity = offering.Section_Size
            
            seatsAvailable = capacity - offering.seatsTaken
            if (offering.Section_Closed_Date == None):
                statusClosed = ''
            else:
                if (todays_date >= offering.Section_Closed_Date):
                    statusClosed = 'C'
                else:
                    statusClosed = ''

            seatsAvailable = capacity - offering.seatsTaken
            if (seatsAvailable > 0):
                statusFull = ''
            else:
                statusFull = 'F'

            fee = offering.courseFee

            if (offering.datesNote == None):
                datesNote = ''
            else:
                datesNote = 'Meets - ' + offering.datesNote

            if (offering.prereq == None):
                prereq = ''
            else:
                prereq = offering.prereq


            offeringItems = {
                'sectionName':offering.courseNumber + '-' + offering.sectionID,
                'term':term,
                'courseNumber':offering.courseNumber,
                'title':offering.title,
                'instructorName':offering.instructorName,
                'dates':offering.Section_Dates,
                'notes':datesNote,
                'capacity':capacity,
                'seatsTaken':offering.seatsTaken,
                'seatsAvailable':seatsAvailable,
                'fee':fee,
                'prereq':prereq,
                'supplies':offering.Section_Supplies,
                'suppliesFee':offering.Section_Supplies_Fee,
                'fullMsg':statusFull,
                'closedMsg':statusClosed
            }     

            # if statusFull != 'F' and statusClosed != 'C':
            offeringDict.append(offeringItems)
        
    return render_template("classLists.html",offeringDict=offeringDict,term=term,displayDate=displayDate)

@app.route("/getCourseMembers", methods=["GET"])
def getCourseMembers():
    specifiedSection = request.args.get('sectionNumber')
    #destination = request.args.get('destination')
    # todays_date = date.today()
    # displayDate = todays_date.strftime('%-B %d, %Y')
    term = db.session.query(ControlVariables.Current_Course_Term).filter(ControlVariables.Shop_Number == 1).scalar()
    
    # BUILD CLASS LISTS ARRAY FOR THE CURRENT TERM
    classListDict = []
    classListItems = []

    try:
        sp = "EXEC classLists '" + term + "'"
        sql = SQLQuery(sp)
        classLists = db.engine.execute(sql)
        
    except (SQLAlchemyError, DBAPIError) as e:
        errorMsg = "ERROR retrieving classLists "
        flash(errorMsg,'danger')
        return 'ERROR in classList list build.'
    
    if classLists == None:
        flash('There are no classLists available for this term.','info')
    else:    
        for classList in classLists:
            memberName = classList.lastName + ', ' + classList.firstName
            if classList.nickName != None and classList.nickName != '':
                memberName += ' (' + classList.nickName + ')'
            sectionName = classList.courseNumber + '-' + classList.sectionID 
            classListItems = {
                'memberName':memberName,
                'sectionName':sectionName,
                'dateEnrolled':classList.dateEnrolled.strftime('%m-%d-%Y'),
                'homePhone':classList.homePhone,
                'cellPhone':classList.cellPhone,
                'eMail':classList.eMail
            }
            if sectionName == specifiedSection:
                classListDict.append(classListItems)
    return jsonify(classListDict=classListDict)        
       

@app.route("/prtClassList", methods=["GET"])
def prtClassList():
    specifiedSection = request.args.get('sectionNumber')
    destination = request.args.get('destination')

    todays_date = date.today()
    displayDate = todays_date.strftime('%-B %d, %Y')
    term = db.session.query(ControlVariables.Current_Course_Term).filter(ControlVariables.Shop_Number == 1).scalar()
    
    # BUILD CLASS LISTS ARRAY FOR THE CURRENT TERM
    classListDict = []
    classListItems = []

    try:
        sp = "EXEC classLists '" + term + "'"
        sql = SQLQuery(sp)
        classLists = db.engine.execute(sql)
        
    except (SQLAlchemyError, DBAPIError) as e:
        errorMsg = "ERROR retrieving classLists "
        flash(errorMsg,'danger')
        return 'ERROR in classList list build.'
    
    if classLists == None:
        flash('There are no classLists available for this term.','info')
    else:    
        for classList in classLists:
            memberName = classList.lastName + ', ' + classList.firstName
            if classList.nickName != None and classList.nickName != '':
                memberName += ' (' + classList.nickName + ')'
            sectionName = classList.courseNumber + '-' + classList.sectionID 
            classListItems = {
                'memberName':memberName,
                'sectionName':sectionName,
                'dateEnrolled':classList.dateEnrolled.strftime('%m-%d-%Y'),
                'homePhone':classList.homePhone,
                'cellPhone':classList.cellPhone,
                'eMail':classList.eMail
            }
            if sectionName == specifiedSection:
                classListDict.append(classListItems)

    courseNumber = specifiedSection[0:4]
    sectionID = specifiedSection[5:6]

    courseTitle = db.session.query(Course.Course_Title).filter(Course.Course_Number == courseNumber).scalar()

    instructorName = 'Not assigned.'
    classDates = 'N/A'
    classTimes = ''
    maxSize = ''
    enrolled = ''
    available = ''

    section = db.session.query(CourseOffering)\
        .filter(CourseOffering.Course_Number == courseNumber)\
        .filter(CourseOffering.Section_ID == sectionID).first()
    if section:
        instructorID =section.Instructor_ID
        member = db.session.query(Member).filter(Member.Member_ID == instructorID).first()
        if member:
            instructorName = member.First_Name
            if member.Nickname != None and member.Nickname != '':
                instructorName += ' (' + member.Nickname + ')'
            instructorName += " " + member.Last_Name
            instructorEmail = member.eMail

        classDates = section.Section_Dates
        classTimes = section.Section_Dates_Note
        maxSize= section.Section_Size
   
        enrolled = db.session.query(func.count(CourseEnrollee.Member_ID))\
            .filter(CourseEnrollee.Course_Term == term)\
            .filter(CourseEnrollee.Course_Number == courseNumber)\
            .filter(CourseEnrollee.Section_ID == sectionID).scalar()

        available = maxSize - enrolled
    html = render_template("rptClassList.html",enrolleeDict=classListDict,\
    sectionNumber=specifiedSection,courseTitle=courseTitle,\
    instructor=instructorName,classDates=classDates,classTimes=classTimes,\
    maxSize=maxSize,enrolled=enrolled,available=available,displayDate=displayDate)        

    if destination != 'PDF':
        return html



    # CREATE PDF FROM HTML VARIABLE
    # use rptClassListPDF for creating PDF; it has no external CSS file
    html = render_template("rptClassListPDF.html",enrolleeDict=classListDict,\
    sectionNumber=specifiedSection,courseTitle=courseTitle,\
    instructor=instructorName,classDates=classDates,classTimes=classTimes,\
    maxSize=maxSize,enrolled=enrolled,available=available,displayDate=displayDate)
    currentWorkingDirectory = os.getcwd()
    pdfDirectoryPath = currentWorkingDirectory + "/app/static/pdf"
    filePath = pdfDirectoryPath + "/rptClassList.pdf"
    options = { 
            'enable-local-file-access': None,
            'quiet':'',
            '--print-media-type':''
        }
    pdfkit.from_string(html,filePath, options=options)



    # GET RECIPIENT
    cc = ''
    subject = 'Class list for ' + specifiedSection
    recipient = instructorEmail
    recipientList = []
    recipientList.append(recipient)
    message = 'Attached is a list of the members enrolled in ' + specifiedSection + '.'
    # SMTPLIB approach; call function sendMail()
    response = sendMail(recipient, subject, message, filePath, html)
    if (response == "ERROR - Message could not be sent."):
        return make_response (f"{response}") 
    else:
        flash("Email sent.",'success')
        return redirect(url_for('ClassLists'))

def sendMail(recipient, subject, message, filePath, html):
    sender = ('frontdesk@thevwc.net')
    password = 'Dove1234'
    msg = MIMEMultipart()
    msg['From'] = sender
    msg['To'] = recipient
    msg['Subject']=subject
    # Attach the message to the MIMEMultipart object
    msg.attach(MIMEText(message, 'plain'))
    pdfName = filePath
    binary_pdf = open(pdfName, 'rb')
    payload = MIMEBase('application', 'octate-stream', Name=pdfName)
    payload.set_payload((binary_pdf).read())
    encoders.encode_base64(payload)
    payload.add_header('Content-Decomposition', 'attachment', filename=pdfName)
    msg.attach(payload)

    # AFTER ADDING ATTACHMENTS, IF ANY
    server = smtplib.SMTP('outlook.office365.com',587)
    server.starttls()
    server.login(sender,password)
    text = msg.as_string() # Convert the MIMEMultipart object to a string to send
    try:
        server.sendmail(sender,recipient,text)
        server.quit()
        response = "Email sent."
        return response
    except (Exception) as e:
        response = "ERROR - Message could not be sent."
        return response  

@app.route('/printTrainingClass', methods=['GET'])
def printTrainingClass():
    # LIST TRAINING CLASS ATTENDEES
    beginDate=request.args.get('beginDate')
    endDate=request.args.get('endDate')
    if beginDate == None or endDate == None:
        flash('The training dates are missing','danger')
        return

    shopNumber=request.args.get('shop')
    #destination = request.args.get('destination')
    beginDateDAT = datetime.strptime(beginDate,'%Y-%m-%d')
    endDateDAT = datetime.strptime(endDate,'%Y-%m-%d')
    displayTrainingDate = beginDateDAT.strftime('%B %-d, %Y') + " - " + endDateDAT.strftime('%B %-d, %Y') 
    
    # GET TODAYS DATE
    todays_date = date.today()
    todaysDate = todays_date.strftime('%B %-d, %Y')
    
    # GET MEMBERS IN TRAINING CLASS
    if (shopNumber == '1'):
        shopName='Rolling Acres'
        members = db.session.query(Member)\
        .filter(Member.Last_Monitor_Training >= beginDate)\
        .filter(Member.Last_Monitor_Training <= endDate)\
        .order_by(Member.Last_Name,Member.First_Name).all()
    else:
        shopName = 'Brownwood'
        members = db.session.query(Member)\
        .filter(Member.Last_Monitor_Training_Shop_2 >= beginDate)\
        .filter(Member.Last_Monitor_Training_Shop_2 <= endDate)\
        .order_by(Member.Last_Name,Member.First_Name).all()
        
    if members == None:
        flash ('No members assigned to this date.','info')
        return redirect(url_for('index'))

    classDict = []
    classItem = []
    
    for m in members:
        displayName = m.Last_Name
        
        if m.Last_Monitor_Training != None:
            lastMonitorTraining = m.Last_Monitor_Training.strftime('%m-%d-%Y')
        else:
            lastMonitorTraining = ''
    

        if m.Nickname != None:
            displayName += ' (' + m.Nickname + ')'
        displayName += ' ' + m.First_Name
    
        classItem = {
            'name': displayName,
            'memberID':m.Member_ID,
            'trainingDate':lastMonitorTraining
        }
        classDict.append(classItem)
    
    return render_template("rptTrainingClass.html",members=members,classDict=classDict,\
    displayTrainingDate=displayTrainingDate,todaysDate=todaysDate,shopName=shopName)

def getStaffID():
	if 'staffID' in session:
		staffID = session['staffID']
	else:
		flash('Login ID is missing.','danger')
		staffID = ''
	return staffID
	
def getShopID():
	if 'shopID' in session:
		shopID = session['shopID']
	else:
		# SET RA FOR TESTING; SEND FLASH ERROR MESSAGE FOR PRODUCTION
		shopID = 'RA'
		msg = "Missing location information; Rolling Acres assumed."
		flash(msg,"danger")
	return shopID 


# def sendMail():
#      # DETERMINE PATH TO PDF FILES
#     currentWorkingDirectory = os.getcwd()
#     dir_path = currentWorkingDirectory + "/app/static/pdf"

#     # GET RECIPIENT
#     cc = request.args.get('coordinatorsEmail')
#     subject = request.args.get('subject')
#     recipient = request.args.get('recipient')
#     recipientList = []
#     recipientList.append(recipient)

#     # SMTPLIB approach
#     sender = ('frontdesk@thevwc.net')
#     password = 'Dove1234'
    
#     subject = request.args.get('subject')
#     message = request.args.get('message')
#     msg = MIMEMultipart()
#     msg['From'] = sender
#     msg['To'] = recipient
#     msg['Subject']=subject
#     # Attach the message to the MIMEMultipart object
#     msg.attach(MIMEText(message, 'plain'))
    
#     # SETUP ATTACHMENTS
#     for f in files:
#         file_path = os.path.join(dir_path,f)
#         # attachment = MIMEApplication(open(file_path, "rb").read(), _subtype="pdf")
#         # attachment.add_header('Content-Disposition', 'attachment', filename=f)
#         # msg.attach(attachment)

#         pdfName = file_path
#         binary_pdf = open(pdfName, 'rb')
#         payload = MIMEBase('application', 'octate-stream', Name=pdfName)
#         payload.set_payload((binary_pdf).read())
#         encoders.encode_base64(payload)
#         payload.add_header('Content-Decomposition', 'attachment', filename=pdfName)
#         msg.attach(payload)

#     # AFTER ADDING ATTACHMENTS, IF ANY
#     server = smtplib.SMTP('outlook.office365.com',587)
#     server.starttls()
#     server.login(sender,password)
#     text = msg.as_string() # Convert the MIMEMultipart object to a string to send

#     server.sendmail(sender,recipient,text)
#     server.quit()

#     response = "Email sent."
#     #except (Exception) as e:
#     #    response = "ERROR - Message could not be sent."
#     return make_response (f"{response}")    
