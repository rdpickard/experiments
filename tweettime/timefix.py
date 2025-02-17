import sys
import re
import configparser
import logging
import random
import hashlib
import string
import os

import arrow
import plotly.express as px
import requests
from atproto import Client, models
from atproto.exceptions import BadRequestError, UnauthorizedError
import plotly.graph_objects as go
from plotly.subplots import make_subplots


atproto_handle_regext = re.compile(r'^([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$')
logger = logging.getLogger()
config = None

def atbot_before_run():
    global config
    global logger

    config = configparser.ConfigParser()
    config.add_section("logging")
    config.add_section("atproto")
    config.add_section("storage")


    config.set("logging", "debug", "True")
    config.set("atproto", "provider protocol", "https")
    #config.set("storage", "image directory url", "file:/Volumes/rdpnas/millennium_every_hour_screenshots")
    config.set("storage", "image directory url", "s3:millennium-every-hour-screenshots")
    # set up a logger
    log_id = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(6))
    logformatter = logging.Formatter(f"%(asctime)s [%(name)s] [%(threadName)s] [%(levelname)s] ({log_id}) %(message)s")
    logger = logging.getLogger()

    consolehandler = logging.StreamHandler()
    consolehandler.setFormatter(logformatter)
    logger.addHandler(consolehandler)

    if config.getboolean("logging", "debug"):
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)


def atbot_get_client(ataccount_handle, ataccount_password):
    global logger
    global config

    # make sure the account handle is well formatted
    if re.match(atproto_handle_regext, ataccount_handle) is None:
        logger.fatal(f"AT account handle '{ataccount_handle}' is invalid for format rules. Bailing")
        sys.exit(-1)

    # look up the DID of the handle
    atserver_handeldid_url = f"https://{ataccount_handle}/.well-known/atproto-did"
    logger.debug(f"AT handel DID URL '{atserver_handeldid_url}'")
    try:
        did_response = requests.get(atserver_handeldid_url)
        if did_response.status_code != 200:
            logger.fatal(f"Request to get DID for handle at URL '{atserver_handeldid_url}' returned status '{did_response.status_code}', 200 is required. Bailing")
            sys.exit(-1)
        else:
            logger.debug(f"DID for '{ataccount_handle}' => '{did_response.text}'")
    except Exception as e:
        logger.fatal(f"Unhandled exception '{e}' in request to get DID for handle at URL '{atserver_handeldid_url}'. Bailing")
        sys.exit(-1)

    # get a client for the handle
    (ataccount_account_name, ataccount_provider_domain) = ataccount_handle.split(".", 1)

    atserver_base_url = f"https://{ataccount_provider_domain}"
    logger.debug(f"AT server base URL '{atserver_base_url}'")
    try:
        client = Client(str(atserver_base_url))
        client.login(ataccount_handle,
                     ataccount_password)
    except UnauthorizedError as aue:
        password_hash_last4 = hashlib.md5(ataccount_password.encode()).hexdigest()[-4:]

        logger.fatal(
            f"Authentication failed for account '{ataccount_handle}' into server '{atserver_base_url}' with password that has md5 hash ending in '{password_hash_last4}'. Bailing")
        sys.exit(-1)

    return client

def get_elon_tweets_xtracker():

    elons_tweets_response = requests.post("https://www.xtracker.io/api/download",
                                          json={"handle":"elonmusk","platform":"X"},
                                          headers={"Content-Type": "application/json"})

    if elons_tweets_response.status_code != 200:
        raise Exception(f"xtracker api download response status code is '{elons_tweets_response.status_code}', requires '200'. Bailing")

    return elons_tweets_response.text

def normalize_xtracker_csv(text_blob, latest_year=arrow.utcnow().year):

    tweet_records=[]

    #entry_regex_string = r'([0-9]),\"([^\"]*)\",\"([a-zA-Z]{3,}) ([\d]+), ([\d]+:[\d]+:[\d]+) ([AMP]+) (.*)\"'
    entry_regex_string = r'(?P<id>[0-9]*),\"(?P<tweet_text>[^\"]*)\",\"(?P<month>[a-zA-Z]{3,}) (?P<day>[\d]+), (?P<time>[\d]+:[\d]+:[\d]+) (?P<period>[AMP]+) (?P<timezone_name>.*)\"'

    entry_regex = re.compile(entry_regex_string, re.MULTILINE)

    matches = re.findall(entry_regex, text_blob)

    year_in_time = latest_year
    previous_line_month_numeric = 13

    for match in reversed(matches):

        ##
        month_numeric = arrow.get(match[2].lower(), "MMM").month
        if month_numeric > previous_line_month_numeric:
            year_in_time = year_in_time - 1
        previous_line_month_numeric = month_numeric

        tstamp = arrow.get(f"{match[2]} {match[3]} {match[4]} {match[5]} {match[6]} {year_in_time}".strip(","), "MMM D H:mm:ss A ZZZ YYYY")

        tweet_records.append((match[0], tstamp, match[1]))

    return tweet_records

def main():
    
    elons_tweets= normalize_xtracker_csv(get_elon_tweets_xtracker())
    """
    elons_tweets= normalize_xtracker_csv("/Users/pickard/Downloads/elonmusk-4.csv")
    
    with open("/Users/pickard/Downloads/elonmusk-4.csv") as tf:
        tblob=tf.read()
    elons_tweets= normalize_xtracker_csv(tblob)
    """

    time_stamps = [t[1] for t in elons_tweets]
    alltweets_points_x = []
    alltweets_points_y = []
    pastthreedaystweets_points_x = []
    pastthreedaystweets_points_y = []
    tweets_per_day = {}

    latest_time_stamps = max(time_stamps)
    three_days_ago = latest_time_stamps.shift(days=-3).replace(hour=0, minute=0, second=0)

    print(three_days_ago)

    for tweet_time in reversed(time_stamps):
        #x=(tweet_time - tweet_times[0]).days
        x=tweet_time.format("MMM DD YYYY")
        y=((tweet_time.hour * 60) + tweet_time.minute)
        #y=tweet_time.format("HH:MM")
        alltweets_points_x.append(x)
        alltweets_points_y.append(y)
        if tweet_time > three_days_ago:
            pastthreedaystweets_points_x.append(x)
            pastthreedaystweets_points_y.append(y)
        if x not in tweets_per_day.keys():
            tweets_per_day[x] = 0
        tweets_per_day[x]+=1


    """
    alltweets_fig = px.scatter(x=alltweets_points_x, y=alltweets_points_y)
    alltweets_fig.add_scatter(x=list(tweets_per_day.keys()), y=list(tweets_per_day.values()), mode='lines', showlegend=False)
    
    alltweets_fig.update_layout(
        yaxis = dict(
            tickmode = 'array',
            tickvals = [x*120 for x in range(0,12)],
            ticktext = ['Midnight', '02:00', '04:00', '06:00', '08:00', '10:00', '12:00', '14:00', '16:00', '18:00', '20:00', '22:00']
        )
    )
    """
    alltweets_fig = make_subplots(specs=[[{"secondary_y": True}]])
    alltweets_fig.add_trace(
        go.Scatter(x=alltweets_points_x, y=alltweets_points_y, name="a tweet", mode="markers"),
        secondary_y=False,
    )
    alltweets_fig.add_trace(
        go.Scatter(x=list(tweets_per_day.keys()), y=list(tweets_per_day.values()), mode="lines+markers", name="tweets per day", opacity=0.5),
        secondary_y=True,
    )

    pastthreedaystweets_fig = px.scatter(x=pastthreedaystweets_points_x, y=pastthreedaystweets_points_y)
    pastthreedaystweets_fig.update_layout(
        yaxis = dict(
            tickmode = 'array',
            tickvals = [x*120 for x in range(0,12)],
            ticktext = ['Midnight', '02:00', '04:00', '06:00', '08:00', '10:00', '12:00', '14:00', '16:00', '18:00', '20:00', '22:00']
        )
    )

    client = atbot_get_client(os.environ.get("ATBOT_AUTH_USERNAME"), os.environ.get("ATBOT_AUTH_PASSWORD"))

    client.send_images(text=f"Elon's tweets per day between {min(time_stamps)} and {max(time_stamps)}",
                      images= [alltweets_fig.to_image(format="png", width=1400, scale=2),  pastthreedaystweets_fig.to_image(format="png")],
                      image_alts=[f"Elon's tweets per day between {min(time_stamps)} and {max(time_stamps)}",
                                  f"Elon's tweets per day between {three_days_ago} and {max(time_stamps)}"])


    #alltweets_fig.show()

    #img_bytes = alltweets_fig.to_image(width=1400, format="png", scale=3)
    #with open("i3.png", 'wb') as new_image_file:
    #    new_image_file.write(img_bytes)
    #sys.exit(0)

print("here")
print(__name__)
if __name__ == "__main__":
    print("here")
    main()