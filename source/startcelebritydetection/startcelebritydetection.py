# ==================================================================================
# Copyright 2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.

# Permission is hereby granted, free of charge, to any person obtaining a copy of this
# software and associated documentation files (the "Software"), to deal in the Software
# without restriction, including without limitation the rights to use, copy, modify,
# merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
# PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
# ==================================================================================
#
# lambda_function.py
# by: Johan Bjørn
# 
#
# ==================================================================================

import cv2
import math
import io

import os
import sys
import json
import random
import datetime
import requests
import boto3
import botocore
import uuid
import string
import collections
from requests.auth import HTTPDigestAuth
from multiprocessing.pool import ThreadPool
from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.core import patch_all
from botocore.config import Config

# Used to surpress warnings
from requests.packages.urllib3.exceptions import InsecureRequestWarning

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

patch_all()

# Used for debugging purposes.
DEBUG = True
# Threading
POOL = ThreadPool(processes=16)
TMP_DIR = '/tmp/'
# Global Bucket for temp storage
BUCKET_NAME = ""
NAME_MODIFIER = '_1280x720_3300k'


# Caption languages getting generated.


# ==================================================================================
# Function: get_mediapackage_password
# Purpose: MediaPackage Password is stored in SSM. I look there to get it in my code. 
# Parameters: 
#               None
# ==================================================================================
def get_mediapackage_password(mediaPackageUsername):
    # SSM manager using the outputChannelUsername to get the MediaPackage Password.
    try:
        client = boto3.client('ssm')
        res = client.get_parameter(Name=mediaPackageUsername)
        mediaPackagePassword = res['Parameter']['Value']
    except Exception as e:
        print("EXCEPTION: Unable to get MediaPackage password from SSM - " + str(e))

    return mediaPackagePassword


# ==================================================================================
# Function: send_to_mediapackage
# Purpose: Uses WebDav with authentication to send files into MediaPackage
# Parameters: 
#               filename - Name of the file you want to be sent to MediaPackage.
#               data - binary data of your file
# ==================================================================================
def send_to_mediapackage(filename, data, pipe_number):
    if pipe_number == 0:
        outputChannelUrl = os.environ['mediaPackageUrlPipe0']
        outputChannelUsername = os.environ['mediaPackageUsernamePipe0']
    else:
        outputChannelUrl = os.environ['mediaPackageUrlPipe1']
        outputChannelUsername = os.environ['mediaPackageUsernamePipe1']

    outputChannelPassword = get_mediapackage_password(outputChannelUsername)
    outputChannelUrl = outputChannelUrl.replace('/channel', '') + "/" + filename
    try:
        response = requests.put(outputChannelUrl, auth=HTTPDigestAuth(outputChannelUsername, outputChannelPassword),
                                data=data, verify=False)
    except Exception as e:
        print("TEST: Exception Pipe number is: " + str(pipe_number))
        print("Output channel url: " + outputChannelUrl)
        print("Output channel username: " + outputChannelUsername)
        print("Output channel Password: " + outputChannelPassword)

        print(str(e))

    # If the response has a 401 error resend the file. 
    if '401' in str(response):
        print('EXCEPTION: Got a 401 response from MediaPackage sending again. ' + str(filename))
        send_to_mediapackage(filename, data, pipe_number)


# ==================================================================================
# Function: make_random_string
# Purpose: Used as a GUID for creating local files.
# Parameters: 
#               none
# ==================================================================================
def make_random_string():
    return ''.join([random.choice(string.ascii_letters + string.digits) for n in range(32)])


# ==================================================================================
# Function: upload_file_s3
# Purpose: Used to upload files to the bucket created by CloudFormation.
# Parameters: 
#               path - Path to file to upload
#               name - s3 key name
# ==================================================================================
def upload_file_s3(path, name):
    s3 = boto3.resource('s3')
    with open(path, 'rb') as data:
        try:
            s3.Bucket(BUCKET_NAME).put_object(Key=name, Body=data)
        except Exception as e:
            print("EXCEPTION: When uploading file to S3 " + str(e))
            return False
    return True


# ==================================================================================
# Function: start_celebrity_rekognition
# Purpose: 
# Parameters:
#               ts_file_path - Path to ts segment
# ==================================================================================
def start_celebrity_rekognition(ts_file_path, pipe_number, duration):
    if (pipe_number == 1):
        return ""

    # Check to make sure that TS file exists
    if not os.path.isfile(ts_file_path):
        print("EXCEPTION: ts file doesn't exist to make " + ts_file_path)
        sys.exit()

    output_mp4 = ts_file_path.replace("ts", "mp4");
    cmd2 = './ffmpeg -i ' + ts_file_path + ' -acodec copy -vcodec copy ' + output_mp4 + '  > /dev/null 2>&1 '
    mp4_ffmpeg_response = os.popen(cmd2).read()

    s3_key2 = 'mp4/' + output_mp4.split('/')[-1]
    upload_file_s3(output_mp4, s3_key2)

    # #call Rekognition
    rek = boto3.client('rekognition')

    # # label-detection
    regkognitionRoleArn = os.environ['regkognitionRoleArn']
    amazonRekognitionTopicArn = os.environ['amazonRekognitionTopicArn']
    print("DEBUG: rekogRole.arn " + regkognitionRoleArn)
    print("DEBUG: amazonRekognitionTopicArn " + amazonRekognitionTopicArn)

    # # celebrity-detection 
    response = rek.start_celebrity_recognition(Video={'S3Object': {'Bucket': BUCKET_NAME, 'Name': s3_key2}},
                                               NotificationChannel={'RoleArn': regkognitionRoleArn,
                                                                    'SNSTopicArn': amazonRekognitionTopicArn}, 
                                                                    JobTag=str(duration)
                                                                    )
    print('Start Job Id, celebrity: ' + response['JobId'] + "s3_key2: " + s3_key2)

    text = ""
    return text


# ==================================================================================
# Function: get_last_segment_name
# Purpose: Gets the last line from a Child Manifest file.
# Parameters: 
#               child_manifest - Child TS file manifest string
# ==================================================================================
def get_last_segment_name(child_manifest):
    child_manifest = child_manifest.split('\n')
    child_manifest.reverse()
    for x in child_manifest:
        if '.ts' in x:
            segment_name = x
            return segment_name
    return "ERROR"


# ==================================================================================
# Function: download_file_from_s3
# Purpose: Downloads file to /tmp/ directory in Lambda
# Parameters: 
#               s3_key - Key of the file you want in S3.
#               bucket_name - Bucket you want the file from.
# ==================================================================================
def download_file_from_s3(s3_key, bucket_name):
    output_dir = TMP_DIR + s3_key.split('/')[-1]
    s3 = boto3.client('s3')
    # Used to wait for the S3 object to exist
    waiter = s3.get_waiter('object_exists')
    try:
        # Used to wait for the S3 object to exist
        waiter.wait(
            Bucket=BUCKET_NAME,
            Key=s3_key,
            WaiterConfig={
                'Delay': 1,
                'MaxAttempts': 6
            }
        )
        s3.download_file(bucket_name, s3_key, output_dir)
    # except botocore.exceptions.ClientError as e:
    except Exception as e:
        print("EXCEPTION: Download file from s3 object does not exist " + str(s3_key) + " ." + str(e))
        # Return from program
        sys.exit()

    return output_dir


def get_s3_file(s3_key):
    if DEBUG:
        print("The S3_key is " + s3_key)
    try:
        s3 = boto3.client('s3')
        # Used to wait for the S3 object to exist
        waiter = s3.get_waiter('object_exists')
        waiter.wait(
            Bucket=BUCKET_NAME,
            Key=s3_key,
            WaiterConfig={
                'Delay': 1,
                'MaxAttempts': 6
            })
        response = s3.get_object(Bucket=BUCKET_NAME, Key=s3_key)
        s3object = response['Body'].read()
    except Exception as e:
        print('EXCEPTION: Getting file called ' + s3_key + ' from S3 exception: ' + str(e))
    return s3object


def get_s3_file_versionid(s3_key, versionid):
    try:
        s3 = boto3.client('s3')
        response = s3.get_object(Bucket=BUCKET_NAME, Key=s3_key, VersionId=versionid)
        s3object = response['Body'].read().decode('utf-8')
    except Exception as e:
        print('EXCEPTION: When getting file from S3 > ' + str(e))

    return s3object


# Send TS file within manifest into the 
def send_ts_file_and_manifest(s3_key, s3_version, pipe_number):
    # Get manifest
    manifest_name = s3_key.split('/')[-1]
    manifest = get_s3_file_versionid(s3_key, s3_version)
    # Get TS filename
    tsfile_name = manifest.split('\n')[-2]

    # Get ts file from S3
    ts_file_s3_key = s3_key.split('/')[0] + '/' + tsfile_name
    tsfile = get_s3_file(ts_file_s3_key)

    # Send both files into MediaPackage
    send_to_mediapackage(tsfile_name, tsfile, pipe_number)
    send_to_mediapackage(manifest_name, manifest, pipe_number)

    return True


# ==================================================================================
# Function: send_vtt_file_and_manifest
# Purpose: Helper function that sends a WebVTT file and Manifest.
# Parameters:
#               child_name - name of the child manifest
#               child_manifest - string that contains the child video manifest
# ==================================================================================
def prepare_start_celebrity_rekognition(child_name, child_manifest, pipe_number):
    using_polly = False

    # Download TS Segment from S3
    ts_segment_name = get_last_segment_name(child_manifest)

    if '#EXT-X-ENDLIST' in ts_segment_name:
        # MediaLive channel was restarted skip this segment.
        print("#EXT-X-ENDLIST found exiting lambda.")
        sys.exit()

    # Download the file from S3. 
    if pipe_number == 1:
        base_name = 'livestream_pipe1/'
    else:
        base_name = 'livestream_pipe0/'

    duration = segment_duration_from_child_manifest(child_manifest)

    print("Segment duration: " + str(duration) + " for " + child_name)

    print("GETTING: Downloading file from S3 for captions trying to get this file : " + base_name + ts_segment_name)
    print("GETTING: Down " + base_name)
    print("GETTING: Down " + ts_segment_name)
    ts_file_path = download_file_from_s3(base_name + ts_segment_name, BUCKET_NAME)

    print("TRANSCRIBE: Getting text from transcribe ")
    # Use TS with FFMPEG to make captions
    text = start_celebrity_rekognition(ts_file_path, pipe_number, duration)

    # Last Clean Up things
    # Remove the TS file that I have been using. 
    try:
        os.remove(ts_file_path)
    except Exception as e:
        print("TS file was not there " + ts_file_path)

    return True

def segment_duration_from_child_manifest(child_manifest):
    lines = child_manifest.split('\n')[:-1]
    # Example string #EXTINF:6.00600,
    for line in lines:
        if '#EXTINF:' in line:
            seconds = int(float(line.replace('#EXTINF:', '').replace(',','')))
            return seconds
    # Default to 6 if no segment length in manifest
    return 6

# ==================================================================================
# Function: lambda_handler
# Purpose: entry point for the system.
# Parameters:
#               event - from lambda
#               context - from lambda
# ==================================================================================
def lambda_handler(event, context):
    child_name = 'channel_name.m3u8'
    message = event['Records'][0]['Sns']["Message"]
    jsonmessage = json.loads(message)
    s3Message = jsonmessage['Records'][0]['s3']
    # Get bucket name
    global BUCKET_NAME
    BUCKET_NAME = s3Message['bucket']['name']

    # S3 trigger is setup to only allow files that are ending in .m3u8 to pass into this lambda. 
    # Get the name of the file that was sent into S3. 
    s3_key = s3Message["object"]["key"]
    s3_version = s3Message['object']['versionId']

    # Figure out if we are working with pipe0 or pipe1 for MediaLive output, and MediaPackage failover.
    if "pipe1" in s3_key:
        # We are working with pipe0 set pipe number to 1
        pipe_number = 1
    else:
        pipe_number = 0

    # Check if the manifest is a master manifest
    if 'channel.m3u8' in s3_key:
        # It is a master manifest. Send the master manifest. 
        print("It is a master manifest. Send the master manifest.")
        original_manifest = get_s3_file_versionid(s3_key, s3_version)
        send_to_mediapackage('channel.m3u8', original_manifest, pipe_number)

    # Check if the file is a child manifest file.
    elif '.m3u8' in s3_key:
        # Check to see if it is the _416x234_200k rendition of the video. This is what I will use for caption generation.
        if NAME_MODIFIER in s3_key:
            # Get child manifest
            manifest_file = get_s3_file_versionid(s3_key, s3_version)
            # Get child name
            manifest_name = s3_key.split('/')[-1]
            print("DEBUG: Get child name, manifest_name" + manifest_name)

            prepare_start_celebrity_rekognition(manifest_name, manifest_file, pipe_number)
            print("Video Rekognition Initialized")

        # Send the TS file within the manifest.
        print("Send the TS file within the manifest.")
        send_ts_file_and_manifest(s3_key, s3_version, pipe_number)
        print("all done")
    return True


def main():
    pass


if __name__ == '__main__':
    main()
