from bs4 import BeautifulSoup
import requests
import re
import numpy as np
from flask import Flask, render_template, redirect, url_for, request
import sklearn
import psycopg2
import psycopg2.extras
import pickle
import yagmail
import time
import threading


#sort by alphabetical in the database, so database is always the same regardless of win predictions
sorted_names_alpha = []
sorted_dict = {}


DATABASE_URL = "..."


app = Flask(__name__)


def scraper():
    threading.Timer(43200, scraper).start() # call every 12 hours, in case nobody visits the site
    
    results = requests.get("https://www.basketball-reference.com/leagues/NBA_2020.html#misc_stats::none").content

    stats = BeautifulSoup(re.sub("<!--|-->","", results.decode("utf-8")), features = "lxml").find("table", {"id":"misc_stats"})
    number_dict = {"data-stat":["off_rtg", "def_rtg", "net_rtg", "pace", "fta_per_fga_pct","fg3a_per_fga_pct","ts_pct","efg_pct","tov_pct","orb_pct","ft_rate","opp_efg_pct","opp_tov_pct","drb_pct","opp_ft_rate"]}
    #stop predictions when every team has played 10 games. 
    winloss_html = stats.findAll("td", attrs = {"data-stat":["wins", "losses"]})
    number_html = stats.findAll("td",attrs =number_dict )
    names_html = stats.findAll("td", attrs = {"data-stat":"team_name"})

    

    names = []
    numbers = []
    season_over=True

    j=0
    total = 0
    continue_scraping= False

    for i in range(len(winloss_html)):
       
        if (winloss_html[i].text!=""):
            if(j%2 == 0):
                total = (int(winloss_html[i].text))
            else:
                total = total + (int(winloss_html[i].text))
                # a team has played less than 10 games - we must keep scraping
                if (total < 10):
                    continue_scraping = True
                    break
                elif (total < 82):
                    season_over=False
                    break


            j = j+1

    
    for i in names_html:
        if(i.text != "League Average"):
            names.append(i.text.replace("*",""))

    count = 0
    teams = 0
    temp = []
    for i in number_html:
        if(count%15 == 0):
            if(teams == 31):
                break
            numbers.append(temp)
            temp = []
            teams = teams + 1
        
        if(i.text != ""):
            temp.append(float(i.text.replace("+","")))
        count = count + 1
    numbers = numbers[1:]
    
    
    if(season_over):
        summarize_season(winloss_html, names)


    if(continue_scraping):
        # save current data to text file
        with open('current_records.p', 'wb') as fp:
            pickle.dump(numbers, fp)

        # return data
        return numbers,names, continue_scraping
    else:
        # grab data from text file, because AI is done predicting
        with open ('current_records.p', 'rb') as fp:
            old_numbers = pickle.load(fp)

        # return the data in the text file instead
        return old_numbers, names, continue_scraping


def summarize_season(html, team_names):
    j=0
    final_standings=[]
    for i in range(len(html)):
        if (html[i].text!=""):
            if(j%2 == 0):
                
                final_standings.append(int(html[i].text))
            j=j+1

    conn = psycopg2.connect(DATABASE_URL, sslmode="require")
    cur = conn.cursor(cursor_factory = psycopg2.extras.DictCursor)
    cur.execute("select * from standings")
    database_data = cur.fetchall()

    with open ('ai_pred.p', 'rb') as fp:
        ai_pred = pickle.load(fp)

    
    ai_pred = {v: k for k, v in ai_pred.items()}
    for i in database_data:
        message="The NBA regular season has ended. Here are the final results. \n \n"

        message = message + "Actual season results: \n \n"
        total_diff= 0
        ai_total_diff = 0

        for k in range(len(team_names)):
            
           
            message = message +  team_names[k]+ ": " + str(final_standings[k]) + " wins" + "\n"

            


        message = message + "\n" + "Your predictions: \n \n"
       
        
        
        for j in range(len(team_names)):
            user_pred=(i[team_names[j].replace(" ", "_").lower()])
            diff =  user_pred - final_standings[j]
            total_diff = total_diff + abs(diff)
            if diff > 0:
                diff = "+" + str(diff)
            
            
           
            
            message = message + team_names[j] + ": " + str(user_pred) +" wins" + "(" + str(diff) + ")" +"\n"
        message = message + "\n" "Total differences (sum of |actual wins - your predictions| for each team): " + str(total_diff) + "\n"
        
        
        message = message + "\n" + "AI predictions: \n \n"

        for a in range(len(team_names)):
            ai_diff =  round(ai_pred[team_names[a]]-final_standings[a],2)
            ai_total_diff = ai_total_diff + abs(ai_diff)
            if ai_diff > 0:
                ai_diff = "+" + str(ai_diff)
            message = message +  team_names[a]+ ": " + str(round(ai_pred[team_names[a]],2)) + " wins"+ "(" +  str(ai_diff) + ")" + "\n"
        message = message + "\n" + "Total differences (sum of |actual wins - AI predictions| for each team): " + str(ai_total_diff) + "\n"
        message = message + "\n" + "Thank you for participating!"
        yag=yagmail.SMTP(user = "nbapredictai@gmail.com", password = "...")
        #send email to all the available emails in the database
        if(i["email"] != ""):
            yag.send(i["email"], "NBAPredict: Final Results", contents = message)
        






""" def train():
    #train from data collected from the 1997 to 2019 seasons (excluding lockout seasons)
    x = np.genfromtxt("advancedstats.csv", delimiter = ",")
    y = np.genfromtxt("wins.csv", delimiter = "\n")


    xtrain,xtest,ytrain,ytest = train_test_split(x,y,test_size = 0.3, random_state =1)

    lin = linear_model.LinearRegression()
    #lin.fit(xtest, ytest)
    
    lin.fit(xtrain,ytrain)
    
    ypred = lin.predict(xtest)

    from sklearn  import metrics

   

    from joblib import dump
    dump(lin, "model.joblib")
    
    return lin """

@app.route('/')
def display():
    
    # scrape current stats
    sample, names, allow_input = scraper()

    

    from joblib import load

    model = load("model.joblib").predict(sample)

    sorted_dict = {}
    for i in range(0,30):
        sorted_dict[float(model[i])] = names[i]


    #sorted dictionary by number of wins. key: number of wins, val: team name
    sorted_dict = dict(sorted(sorted_dict.items(), reverse = True))

    with open('ai_pred.p', 'wb') as fp:
        pickle.dump(sorted_dict, fp)
    


    

    #nicely formatted display results
    display_ai_predictions = []
    
    #sorted names by win
    sorted_names_win = list()

    for i in sorted_dict:
        
        sorted_names_win.append(sorted_dict[i])
        display_ai_predictions.append((sorted_dict[i] + ": " + str(round(i,2)) + " wins"))

    global sorted_names_alpha

    sorted_names_alpha = sorted_names_win.copy()

    # sort by alphabetical
    sorted_names_alpha.sort()
    
    # only run once to create the initial database table
    #create()


    conn = psycopg2.connect(DATABASE_URL, sslmode="require")
    cur = conn.cursor(cursor_factory = psycopg2.extras.DictCursor)
    cur.execute("select * from standings")
    database_data = cur.fetchall()
    database_data = database_data[::-1] # reverse data so most recent shows up first


    
    
    return render_template("index.html", ai_predictions = display_ai_predictions, human_predictions = database_data, sorted_names_win = sorted_names_win, allow_input = allow_input)

def create():
    global sorted_names_alpha
   

    command = "("
    for i in range(0,30):
        
        sorted_names_alpha[i] = sorted_names_alpha[i].replace(" ", "_")
        command = command + sorted_names_alpha[i] + " int, "


    conn = psycopg2.connect(DATABASE_URL, sslmode="require")
    command = command[:-2]
    command = command + ", email text)"

    cur = conn.cursor()
    cur.execute("CREATE TABLE standings " + command)
    conn.commit()
    conn.close()
    


@app.route('/add',methods = ["POST"])
def add():
    global sorted_names_alpha
    
    insert_data = [] #receive data from form, then insert into database
    
    if request.method == "POST":

        for i in range(0,30):
            
            insert_data.append(request.form.get(sorted_names_alpha[i].replace("_", " ")))
            


        #check if email is empty or not
        email_address = request.form.get("email")
        insert_data.append(email_address)
        if email_address != "":
            send_email(insert_data)
    
                
        
        insert_data = tuple(insert_data)
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        
        cur = conn.cursor()
        cur.execute("INSERT INTO standings VALUES "+ str(insert_data))
        conn.commit()
        conn.close()

            



    return redirect(url_for('display'))

def send_email(entries):
    #send a receipt of predictions


    #key: name of team, value: number of wins
    name_number_dict = {}

    for i in range(30):
        name_number_dict[sorted_names_alpha[i]] = int(entries[i])
    name_number_dict = sorted(name_number_dict.items(), key = lambda x:x[1],reverse=True )


    body = "Here are the predictions you made for this NBA season: \n \n"
    for i in name_number_dict:
        body = body + i[0] + ": " + str(i[1]) + " wins" + "\n"

    



    
    yag=yagmail.SMTP(user = "nbapredictai@gmail.com", password = "...")



    yag.send(entries[30], "NBAPredict: Your NBA Predictions", contents = body)

    
if __name__ == '__main__':
    app.run()
    
    

    

