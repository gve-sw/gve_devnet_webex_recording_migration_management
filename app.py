# !/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Copyright (c) 2022 Cisco and/or its affiliates.
This software is licensed to you under the terms of the Cisco Sample
Code License, Version 1.1 (the "License"). You may obtain a copy of the
License at
               https://developer.cisco.com/docs/licenses
All use of the material herein must be in accordance with the terms of
the License. All rights not expressly granted by the License are
reserved. Unless required by applicable law or agreed to separately in
writing, software distributed under the License is distributed on an "AS
IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
or implied.
"""

__author__ = "Simon Fang <sifang@cisco.com>"
__copyright__ = "Copyright (c) 2022 Cisco and/or its affiliates."
__license__ = "Cisco Sample Code License, Version 1.1"

import requests, urllib

from flask import Flask, request, redirect, render_template
from boto3 import resource
from dotenv import load_dotenv
import os


########################
### Global variables ###
########################

WEBEX_BASE_URL = "https://webexapis.com/v1"

# load environment variables
load_dotenv()

# Webex integration credentials
webex_integration_client_id = os.getenv("webex_integration_client_id")
webex_integration_client_secret= os.getenv("webex_integration_client_secret")
webex_integration_redirect_uri = os.getenv("webex_integration_redirect_uri")
webex_integration_scope = os.getenv("webex_integration_scope")

# AWS Variables
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
REGION_NAME = os.getenv("REGION_NAME")
BUCKET_NAME = os.getenv("BUCKET_NAME")

# Flask app
app = Flask(__name__)

s3 = resource(
    's3',
    aws_access_key_id     = AWS_ACCESS_KEY_ID,
    aws_secret_access_key = AWS_SECRET_ACCESS_KEY,
    region_name           = REGION_NAME
    )

sites = []
selected_site = ""
meetings = []
people = []
selected_person_id = ""

########################
### Helper Functions ###
########################

# Get Webex Access Token
def get_webex_access_token(webex_code):
    headers_token = {
        "Content-type": "application/x-www-form-urlencoded"
    }
    body = {
        'client_id': webex_integration_client_id,
        'code': webex_code,
        'redirect_uri': webex_integration_redirect_uri,
        'grant_type': 'authorization_code',
        'client_secret': webex_integration_client_secret
    }
    get_token = requests.post(WEBEX_BASE_URL + "/access_token?", headers=headers_token, data=body)

    webex_access_token = get_token.json()['access_token']
    return webex_access_token

# Get all the sites
def get_sites():
    # Get site URLs
    url = f"{WEBEX_BASE_URL}/meetingPreferences/sites"
    headers = {
        "Authorization" : f"Bearer {webex_access_token}"
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    sites = response.json()['sites']
    return sites

# Get all the meetings from a selected period, site and specific user in your organization
def get_meetings(from_date, to_date, selected_site, host_email):
    # Get recordings
    url = f"{WEBEX_BASE_URL}/recordings?from={from_date}T00%3A00%3A00&to={to_date}T23%3A59%3A59&siteUrl={selected_site}&hostEmail={host_email}"
    headers = {
        "Authorization" : f"Bearer {webex_access_token}"
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    meetings = response.json()['items']
    return meetings

# Function to return recordings stored in the AWS S3 bucket
def get_aws_recordings():
    aws_recordings = []
    for bucket_obj in s3.Bucket(BUCKET_NAME).objects.all():
        # Format of aws_recordings name: 'topic---id.mp4'
        # Extract ID from title of recording
        try:
            aws_recordings.append((bucket_obj.key.split('.')[0]).split('---')[1])
        except:
            app.logger.info(f"Found a recording in AWS in the wrong format: {bucket_obj.key}")

    return aws_recordings

# Function to check whether a meetings has been migrated to AWS already or not
def are_meetings_in_aws_cloud(meetings, aws_recordings):
    for meeting in meetings:
        # Check if meeting has been migrated to AWS already or not
        if meeting["id"] in aws_recordings:
            meeting["inAWSCloud"] = True
        else:
            meeting["inAWSCloud"] = False
    return meetings

# Get all the people in your organization
def get_people(webex_access_token):
    # Get people
    url = f"{WEBEX_BASE_URL}/people"
    headers = {
        "Authorization" : f"Bearer {webex_access_token}"
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    people = response.json()['items']
    return people
    
# Get the host email from the people details
def get_host_email(person_id):
    # Get people details
    url = f"{WEBEX_BASE_URL}/people/{person_id}"
    headers = {
        "Authorization" : f"Bearer {webex_access_token}"
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    print("get host email")
    print(response.json())
    emails = response.json()["emails"]
    return emails

# Delete a specific webex recording based on the recording ID
def delete_webex_recordings(recording_id, host_email):
    # Delete recording
    url = f"{WEBEX_BASE_URL}/recordings/{recording_id}?hostEmail={host_email}"
    headers = {
        "Authorization" : f"Bearer {webex_access_token}"
    }

    response = requests.delete(url, headers=headers)
    print("delete recording response")
    print(response.status_code)
    return response

# Get the recording details based on a meeting_id
def get_recording_details(meeting, selected_person_id):
    # Get recording details
    url = f"{WEBEX_BASE_URL}/recordings/{meeting}?hostEmail={get_host_email(selected_person_id)[0]}"
    response = requests.get(url, headers = {
        "Authorization" : f"Bearer {webex_access_token}"
    })
    return response.json()

##############
### Routes ###
##############

# login page
@app.route('/')
def mainpage():
    return render_template('mainpage_login.html')

# scheduler page
@app.route('/scheduler')
def scheduler_page():
    global webex_access_token
    sites = get_sites()
    people =  get_people(webex_access_token)
    return render_template('scheduler.html', sites=sites, people=people)

# webex access token
@app.route('/webexlogin', methods=['POST'])
def webexlogin():
    WEBEX_USER_AUTH_URL = WEBEX_BASE_URL + "/authorize?client_id={client_id}&response_type=code&redirect_uri={redirect_uri}&response_mode=query&scope={scope}".format(
        client_id=urllib.parse.quote(webex_integration_client_id),
        redirect_uri=urllib.parse.quote(webex_integration_redirect_uri),
        scope=urllib.parse.quote(webex_integration_scope)
    )

    return redirect(WEBEX_USER_AUTH_URL)

# Main page of the app
@app.route('/webexoauth', methods=['GET'])
def webexoauth():
    global sites
    global webex_access_token
    global people

    webex_code = request.args.get('code')
    webex_access_token = get_webex_access_token(webex_code)

    sites = get_sites()
    people =  get_people(webex_access_token)

    return render_template('columnpage.html', sites=sites, people=people)

# Step 1: select period of recordings
@app.route('/select_period', methods=['POST', 'GET'])
def select_period():
    global sites
    global selected_site
    global selected_person_id
    global meetings

    if request.method == 'POST':
        form_data = request.form
        app.logger.info(form_data)

        from_date = form_data['fromdate']
        to_date = form_data['todate']
        selected_site = form_data['site']
        selected_person_id = form_data['person']
        host_email = get_host_email(selected_person_id)[0]

        meetings = get_meetings(from_date, to_date, selected_site, host_email)

        app.logger.info("Successfully retrieved the list of recordings")

        # Get recordings in AWS
        aws_recordings = get_aws_recordings()

        meetings = are_meetings_in_aws_cloud(meetings, aws_recordings)

        return render_template('columnpage.html', sites=sites, selected_site = selected_site, meetings = meetings, people=people, selected_person_id=selected_person_id)
    return render_template('columnpage.html')

# Step 2: Select recordings to migrate from Webex to AWS
@app.route('/select_recordings', methods=['POST', 'GET'])
def select_recordings():
    global sites
    global selected_site
    global meetings

    if request.method == 'POST':
        form_data = request.form
        app.logger.info(form_data)

        failed_migration_IDs = []
        meetings_to_migrate = []

        if 'meeting_id' in form_data:
            form_dict = dict(form_data.lists())
            meetings_to_migrate = form_dict['meeting_id']
            app.logger.info(meetings_to_migrate)

            for meeting in meetings_to_migrate:
                try:
                    recording_details = get_recording_details(meeting, selected_person_id)

                    app.logger.info(f"Downloading recording with meeting ID: {meeting}")

                    # Download recording mp4 in memory
                    downloadlink = recording_details['temporaryDirectDownloadLinks']['recordingDownloadLink']
                    topic = recording_details['topic']
                    downloaded_file = urllib.request.urlopen(downloadlink)

                    # We downloaded the file in memory and pass that on to S3 immediately
                    s3.Bucket(BUCKET_NAME).put_object(Key=f'{topic}---{meeting}.mp4', Body=downloaded_file.read())
                except:
                    app.logger.exception(f"Failed migration of recording with meeting id {meeting}")
                    failed_migration_IDs.append(meeting)

        # Get recordings in AWS
        aws_recordings = get_aws_recordings()

        meetings = are_meetings_in_aws_cloud(meetings, aws_recordings)

        failed_migrations = []
        for failed_migration_ID in failed_migration_IDs:
            for meeting in meetings:
                if failed_migration_ID == meeting["id"]:
                    failed_migrations.append(meeting)

        # Return a list of dictionaries with meeting ID and title
        migrated_meetings = []
        for migrated_meeting_id in meetings_to_migrate:
            if migrated_meeting_id in failed_migration_IDs:
                continue
            for meeting in meetings:
                if migrated_meeting_id == meeting["id"]:
                    migrated_meetings.append(meeting)

        # Delete recordings from the Webex cloud
        for meeting in migrated_meetings:
            if delete_webex_recordings(meeting["id"], get_host_email(selected_person_id)[0]).ok:
                app.logger.info(f"Successfully deleted meeting with meeting id {meeting['id']}")

        s3_bucket_link = f"https://s3.console.aws.amazon.com/s3/buckets/{BUCKET_NAME}?region={REGION_NAME}&tab=objects"

        return render_template('columnpage.html', sites=sites, selected_site = selected_site, meetings = meetings, migrated_meetings=migrated_meetings, failed_migrations=failed_migrations, s3_bucket_link=s3_bucket_link, people=people, selected_person_id=selected_person_id)
    return render_template('columnpage.html')

if __name__ == "__main__":
    app.run(debug=False)
