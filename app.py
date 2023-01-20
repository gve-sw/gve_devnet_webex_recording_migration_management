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

import requests
import urllib
import glob


from flask import Flask, request, redirect, render_template, session
from boto3 import resource
from dotenv import load_dotenv
import os
from webexteamssdk import WebexTeamsAPI
import json


########################
### Global variables ###
########################

WEBEX_BASE_URL = "https://webexapis.com/v1"

# load environment variables
load_dotenv()

# Webex integration credentials
webex_integration_client_id = os.getenv("webex_integration_client_id")
webex_integration_client_secret = os.getenv("webex_integration_client_secret")
webex_integration_redirect_uri = os.getenv("webex_integration_redirect_uri")
webex_integration_scope = os.getenv("webex_integration_scope")

# AWS Variables
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
REGION_NAME = os.getenv("REGION_NAME")
BUCKET_NAME = os.getenv("BUCKET_NAME")

DOWNLOAD_FOLDER = os.getenv("DOWNLOAD_FOLDER")
MIGRATE_RECORDINGS = os.getenv("MIGRATE_RECORDINGS")

# Flask app
app = Flask(__name__)

app.secret_key = '123456789012345678901234'


if (AWS_ACCESS_KEY_ID != ""):
    s3 = resource(
        's3',
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=REGION_NAME
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
    get_token = requests.post(
        WEBEX_BASE_URL + "/access_token?", headers=headers_token, data=body)

    webex_access_token = get_token.json()['access_token']
    return webex_access_token

# Get all the sites


def get_sites():
    # Get site URLs
    url = f"{WEBEX_BASE_URL}/meetingPreferences/sites"
    headers = {
        "Authorization": f"Bearer {webex_access_token}"
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
        "Authorization": f"Bearer {webex_access_token}"
    }

    response = requests.get(url, headers=headers)
    if (response.status_code == 401):
        print('Unauthorized!')
        return []
    else:
        response.raise_for_status()
    meetings = response.json()['items']
    return meetings

# Function to return recordings stored in the AWS S3 bucket or local folder


def get_stored_recordings():
    stored_recordings = []
    if (AWS_ACCESS_KEY_ID != ""):
        for bucket_obj in s3.Bucket(BUCKET_NAME).objects.all():
            # Format of stored_recordings name: 'topic---id.mp4'
            # Extract ID from title of recording
            try:
                stored_recordings.append(
                    (bucket_obj.key.split('.')[0]).split('---')[1])
            except:
                app.logger.info(
                    f"Found a recording in AWS in the wrong format: {bucket_obj.key}")
    elif (DOWNLOAD_FOLDER != ""):
        for file in glob.glob(DOWNLOAD_FOLDER+"*.mp4"):
            # Format of stored_recordings name: 'topic---id.mp4'
            # Extract ID from filename of recording
            try:
                stored_recordings.append(
                    (file.split('.')[0]).split('---')[1])
            except:
                app.logger.info(
                    f"Found a recording in local storage in the wrong format: {file}")
    return stored_recordings

# Function to check whether a meetings has been migrated to AWS already or not


def are_meetings_in_storage(meetings, stored_recordings):
    for meeting in meetings:
        # Check if meeting has been migrated or copied to storage already or not
        if meeting["id"] in stored_recordings:
            meeting["inStorage"] = True
        else:
            meeting["inStorage"] = False
    return meetings

# Get all the people in your organization


def get_people(webex_access_token):
    # Get people

    api = WebexTeamsAPI(access_token=webex_access_token)
    people = []
    peopleiterable = api.people.list()
    for person in peopleiterable:
        people.append(json.loads(json.dumps(person.json_data)))
    # print(people)

    return people

# Get the host email from the people details


def get_host_email(person_id):
    # Get people details
    url = f"{WEBEX_BASE_URL}/people/{person_id}"
    headers = {
        "Authorization": f"Bearer {webex_access_token}"
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    # print("get host email")
    # print(response.json())
    emails = response.json()["emails"]
    print(f'Got host email: {emails}')
    return emails


def get_host_email_name(person_id):
    # Get people details
    url = f"{WEBEX_BASE_URL}/people/{person_id}"
    headers = {
        "Authorization": f"Bearer {webex_access_token}"
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    # print("get host email")
    # print(response.json())
    emails = response.json()["emails"]
    displayName = response.json()["displayName"]
    print(f'Got host email: {emails}')
    return emails, displayName

# Delete a specific webex recording based on the recording ID


def delete_webex_recordings(recording_id, host_email):
    # Delete recording
    url = f"{WEBEX_BASE_URL}/recordings/{recording_id}?hostEmail={host_email}"
    headers = {
        "Authorization": f"Bearer {webex_access_token}"
    }

    response = requests.delete(url, headers=headers)
    print("delete recording response")
    print(response.status_code)
    return response

# Get the recording details based on a meeting_id


def get_recording_details(meeting, selected_person_id):
    # Get recording details
    url = f"{WEBEX_BASE_URL}/recordings/{meeting}?hostEmail={get_host_email(selected_person_id)[0]}"
    response = requests.get(url, headers={
        "Authorization": f"Bearer {webex_access_token}"
    })
    return response.json()


def get_recording_details_host_email(meeting, host_email):
    # Get recording details
    url = f"{WEBEX_BASE_URL}/recordings/{meeting}?hostEmail={host_email}"
    response = requests.get(url, headers={
        "Authorization": f"Bearer {webex_access_token}"
    })
    return response.json()


##############
### Routes ###
##############

# login page


@app.route('/')
def mainpage():
    session['bulk'] = False
    return render_template('mainpage_login.html')


# bulk download login
@app.route('/bulk')
def bulk_mainpage():
    session['bulk'] = True
    return render_template('mainpage_login.html')

# scheduler page


@app.route('/scheduler')
def scheduler_page():
    global webex_access_token
    sites = get_sites()
    people = get_people(webex_access_token)
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

    if session['bulk']:
        return render_template('bulkpage.html', sites=sites,
                               Action="Migrate" if (
                                   MIGRATE_RECORDINGS == "True") else "Copy",
                               Destination="AWS" if (AWS_ACCESS_KEY_ID != "") else "Local")
    else:
        people = get_people(webex_access_token)
        return render_template('columnpage.html', sites=sites, people=people,
                               Action="Migrate" if (
                                   MIGRATE_RECORDINGS == "True") else "Copy",
                               Destination="AWS" if (AWS_ACCESS_KEY_ID != "") else "Local")

# Step 1: select period of recordings


@app.route('/select_period', methods=['POST', 'GET'])
def select_period():
    global sites
    global selected_site
    global selected_person_id
    global meetings
    global people

    if request.method == 'POST':
        form_data = request.form
        app.logger.info(form_data)

        from_date = form_data['fromdate']
        to_date = form_data['todate']
        selected_site = form_data['site']

        if session['bulk']:

            # Get recordings in storage
            stored_recordings = get_stored_recordings()
            print(f'Stored recordings: {stored_recordings}')
            app.logger.info(
                "Retrieving all users for bulk download....")
            print("Retrieving all users for bulk download...")
            people = get_people(webex_access_token)
            app.logger.info(
                "Retrieving list of recordings for each user....")
            print("Retrieving list of recordings for each user...")
            for person in people:
                selected_person_id = person['id']
                print(f'Listing recordings for: {selected_person_id}')
                host_details = get_host_email_name(selected_person_id)
                host_email = host_details[0][0]
                host_name = host_details[1]
                user_recordings = get_meetings(from_date,
                                               to_date, selected_site, host_email)
                recordings_not_stored = []
                for user_rec in user_recordings:
                    if user_rec["id"] not in stored_recordings:
                        user_rec["host_email"] = host_email
                        user_rec["host_name"] = host_name
                        recordings_not_stored.append(user_rec)
                meetings += recordings_not_stored

            app.logger.info(
                "Successfully retrieved the list of recordings not already stored for bulk processing")
            print(
                "Successfully retrieved the list of recordings not already stored for bulk processing")

            failed_migrations = []
            migrated_meetings = []
            for meeting in meetings:
                meeting_id = meeting["id"]
                try:
                    recording_details = get_recording_details_host_email(
                        meeting["id"], meeting["host_email"])

                    # Download recording mp4 in memory
                    downloadlink = recording_details['temporaryDirectDownloadLinks']['recordingDownloadLink']
                    topic = recording_details['topic']
                    timerecorded = recording_details['timeRecorded']
                    hostName = meeting["host_name"]
                    filename = f'{hostName}-{timerecorded}---{meeting_id}.mp4'
                    downloaded_file = urllib.request.urlopen(downloadlink)
                    app.logger.info(
                        f"Attempting bulk download of recording ID: {meeting_id} to filename {filename}")
                    print(
                        f"Attempting bulk download of recording ID: {meeting_id} to filename {filename}")
                    if (AWS_ACCESS_KEY_ID != ""):
                        # We downloaded the file in memory and pass that on to S3 immediately
                        s3.Bucket(BUCKET_NAME).put_object(
                            Key=filename, Body=downloaded_file.read())
                        migrated_meetings.append(
                            {"id": meeting_id, "filename": filename})
                    elif (DOWNLOAD_FOLDER != ""):
                        downloaded_file = urllib.request.urlopen(downloadlink)
                        save_as = DOWNLOAD_FOLDER + filename
                        content = downloaded_file.read()
                        # Save to file
                        with open(save_as, 'wb') as download:
                            download.write(content)
                        migrated_meetings.append(
                            {"id": meeting_id, "filename": filename})

                except:
                    app.logger.exception(
                        f"Failed copying of recording with meeting id {meeting_id}")
                    failed_migrations.append(
                        {"id": meeting_id, "filename": filename})

            recordings_summary = f"Copied: {migrated_meetings}  Failed: {failed_migrations}"

            return render_template('bulkpage.html', sites=sites, selected_site=selected_site, recordings_summary=recordings_summary)
        else:
            selected_person_id = form_data['person']
            print(f'Selected person ID: {selected_person_id}')
            if selected_person_id != 'all':
                host_email = get_host_email(selected_person_id)[0]
                meetings = get_meetings(
                    from_date, to_date, selected_site, host_email)
            else:
                for person in people:
                    selected_person_id = person['id']
                    print(f'Listing recordings for: {selected_person_id}')
                    host_email = get_host_email(selected_person_id)[0]
                    meetings += get_meetings(from_date,
                                             to_date, selected_site, host_email)

            app.logger.info("Successfully retrieved the list of recordings")
            print("Successfully retrieved the list of recordings")
            # Get recordings in storage
            stored_recordings = get_stored_recordings()

            meetings = are_meetings_in_storage(meetings, stored_recordings)
            return render_template('columnpage.html', sites=sites, selected_site=selected_site, meetings=meetings, people=people, selected_person_id=selected_person_id,
                                   Action="Migrate" if (
                                       MIGRATE_RECORDINGS == "True") else "Copy",
                                   Destination="AWS" if (AWS_ACCESS_KEY_ID != "") else "Local")
    if session['bulk']:
        return render_template('bulkpage.html')
    else:
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
                    recording_details = get_recording_details(
                        meeting, selected_person_id)

                    app.logger.info(
                        f"Downloading recording with meeting ID: {meeting}")

                    # Download recording mp4 in memory
                    downloadlink = recording_details['temporaryDirectDownloadLinks']['recordingDownloadLink']
                    topic = recording_details['topic']
                    downloaded_file = urllib.request.urlopen(downloadlink)

                    if (AWS_ACCESS_KEY_ID != ""):
                        # We downloaded the file in memory and pass that on to S3 immediately
                        s3.Bucket(BUCKET_NAME).put_object(
                            Key=f'{topic}---{meeting}.mp4', Body=downloaded_file.read())
                    elif (DOWNLOAD_FOLDER != ""):
                        downloaded_file = urllib.request.urlopen(downloadlink)
                        save_as = DOWNLOAD_FOLDER+f'{topic}---{meeting}.mp4'
                        content = downloaded_file.read()
                        # Save to file
                        with open(save_as, 'wb') as download:
                            download.write(content)

                except:
                    app.logger.exception(
                        f"Failed copying of recording with meeting id {meeting}")
                    failed_migration_IDs.append(meeting)

        # Get recordings in storage
        stored_recordings = get_stored_recordings()

        meetings = are_meetings_in_storage(meetings, stored_recordings)

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

        if (MIGRATE_RECORDINGS == "True"):
            # Delete recordings from the Webex cloud
            for meeting in migrated_meetings:
                if delete_webex_recordings(meeting["id"], get_host_email(selected_person_id)[0]).ok:
                    app.logger.info(
                        f"Successfully deleted meeting with meeting id {meeting['id']}")

        if (AWS_ACCESS_KEY_ID != ""):
            s3_bucket_link = f"https://s3.console.aws.amazon.com/s3/buckets/{BUCKET_NAME}?region={REGION_NAME}&tab=objects"
        else:
            s3_bucket_link = f"file://{DOWNLOAD_FOLDER}"

        return render_template('columnpage.html', sites=sites, selected_site=selected_site, meetings=meetings, migrated_meetings=migrated_meetings,
                               failed_migrations=failed_migrations, s3_bucket_link=s3_bucket_link, people=people, selected_person_id=selected_person_id,
                               Action="Migrate" if (
                                   MIGRATE_RECORDINGS == "True") else "Copy",
                               Destination="AWS" if (AWS_ACCESS_KEY_ID != "") else "Local")
    return render_template('columnpage.html')


if __name__ == "__main__":
    app.run(debug=False, port=5500)
