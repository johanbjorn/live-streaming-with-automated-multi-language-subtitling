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
# indentify_custom_labels.py
# by: Johan Bjørn
#
# Purpose: Proof of concept identifying custom labels from a MediaLive  stream using
#          AWS Rekognition Imange. Services used include S3 with versioning, 
#          cloud watch events, lambda, and CloudFront.

# ==================================================================================

import cv2
import math
import io
import os
import sys
import json
import random
import boto3
import botocore
import uuid
import requests
import elasticsearch
import string
import collections
import requests_aws4auth
from requests_aws4auth import AWS4Auth
from requests.auth import HTTPDigestAuth
from multiprocessing.pool import ThreadPool
from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.core import patch_all
from botocore.config import Config
from elasticsearch import Elasticsearch, RequestsHttpConnection

from datetime import datetime, timedelta
import datetime as dtime

# Used to surpress warnings
from requests.packages.urllib3.exceptions import InsecureRequestWarning

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

patch_all()

# Logging
# EXCEPTION for exceptions
TRANSCRIBE_LAMBDA_ARN = os.environ.get('transcribeLambdaARN')

# Used for debugging purposes.
DEBUG = True
TMP_DIR = '/tmp/'
# Global Bucket for temp storage
BUCKET_NAME = ""
NAME_MODIFIER = '_1280x720_3300k'

def analyze_video(videoFile):
    print("analyze_video v1")

    host = 'https://' + os.environ['ESDomain'] + '/'
    index = os.environ['INDX']
    path = 'custom_labels2' + index + '/_doc'  # the Elasticsearch API endpoint
    print("frameRate {}".format(path))
    region = 'us-east-1'  # For example, us-west-1

    service = 'es'
    credentials = boto3.Session().get_credentials()
    awsauth = AWS4Auth(credentials.access_key, credentials.secret_key, region, service, session_token=credentials.token)

    url = host + path

    projectVersionArn = os.environ['REKOGNITIONMODEL']
    rekognition = boto3.client('rekognition')
    customLabels = []

    str2 = videoFile.split('/')[2]
    str3 = str2.split('_')[3]
    int1 = int(str3.split('.')[0])
    
    multiplyer = 1
    if (int1 < 1345):
        multiplyer = 0.8
    else:
        multiplyer = 1.2

    cap = cv2.VideoCapture(videoFile)
    frameRate = cap.get(5)  # frame rate
    print("cap.isOpened() {}".format(cap.isOpened()))
    print("frameRate {}".format(frameRate))
    string2 = videoFile.split("_")[3]
    nrmp4file = int(string2.split(".")[0])
    seconds = int(nrmp4file) * 6006
    numberCallsToRekognition = 0
    while (cap.isOpened()):
        frameId = cap.get(1)  # current frame number
        # print("Processing frame id: {}".format(frameId))
        ret, frame = cap.read()
        if (ret != True):
            break
        if (frameId % math.floor(frameRate) == 0):
            try:
                numberCallsToRekognition = numberCallsToRekognition + 1    
                hasFrame, imageBytes = cv2.imencode(".jpg", frame)
                if (hasFrame):
                    response = rekognition.detect_custom_labels(
                        Image={
                            'Bytes': imageBytes.tobytes(),
                        },
                        ProjectVersionArn=projectVersionArn
                    )
                for elabel in response["CustomLabels"]:
                    elabel["videofile"] = videoFile
                    elabel["Timestamp"] = seconds
                    elabel["Confidence"] = elabel["Confidence"] * multiplyer
                    if (elabel["Confidence"] > 100):
                        elabel["Confidence"] = 100
                    if (1 == 1):

                        for i in range(10):
                            idx = i - 3
                            altSeconds = seconds + (6006 * idx)
                            dt = dtime.datetime.fromtimestamp(altSeconds / 1000)
                            # print(dt)
                            # print("hour: {}".format(dt.hour))
                            # print("minute: {}".format(dt.minute))
                            # print("seconds: {}".format(dt.second))

                            date_time_str1 = os.environ['CHANNELSTARTTIME']
                            date_time_obj1 = datetime.strptime(date_time_str1, '%Y-%m-%dT%H:%M:%S')

                            #print(date_time_obj1)

                            date_time_obj1 = date_time_obj1 + timedelta(hours=dt.hour)
                            date_time_obj1 = date_time_obj1 + timedelta(minutes=dt.minute)
                            date_time_obj1 = date_time_obj1 + timedelta(seconds=dt.second)
                            date_time_obj2 = date_time_obj1 + timedelta(minutes=1)
                            linkKey = "Link-" + str(i)
                            elabel[linkKey] = os.environ['HLS_CF'] + "?start=" + date_time_obj1.strftime(
                                '%Y-%m-%dT%H:%M:%S') + "&end=" + date_time_obj2.strftime('%Y-%m-%dT%H:%M:%S')

                        #print("append label xyz")
                        r = requests.post(url, auth=awsauth,
                                          json=elabel)  # requests.get, post, and delete have similar syntax
                        print("after call to esdomain")
                        print(r.text)
                        customLabels.append(elabel)
            except:
                print("Oops!", sys.exc_info()[0], "occurred.")
                print("Next entry.")
                print()
    print(customLabels)
    print("numberCallsToRekognition: {}".format(numberCallsToRekognition))
    with open(videoFile + ".json", "w") as f:
        f.write(json.dumps(customLabels))

    cap.release()


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
# Function: get_text_from_transcribe
# Purpose: Calls API of Transcribe Streaming Lambda. Gets text from TS Segment.
# Parameters:
#               ts_file_path - Path to ts segment
# ==================================================================================
def prepare_analyze_video(ts_file_path):
    # Check to make sure that TS file exists
    if not os.path.isfile(ts_file_path):
        print("EXCEPTION: ts file doesn't exist to make PCM file for Transcribe : " + ts_file_path)
        sys.exit()

    # to mp4
    print("DEBUG: to mp4 ")
    # output_mp4 = TMP_DIR + str(make_random_string()) + '.mp4'
    output_mp4 = ts_file_path.replace("ts", "mp4");
    cmd2 = './ffmpeg -i ' + ts_file_path + ' -acodec copy -vcodec copy ' + output_mp4 + '  > /dev/null 2>&1 '
    mp4_ffmpeg_response = os.popen(cmd2).read()
    print("DEBUG: mp4_ffmpeg_response " + mp4_ffmpeg_response)
    # After FFMPEG send the file into S3 and generate presigned URL.
    print("checking to see if mp4 exists " + output_mp4 + ' ' + str(os.path.exists(output_mp4)))

    analyze_video(output_mp4)

    s3_key2 = 'mp4/' + output_mp4.split('/')[-1]
    upload_file_s3(output_mp4, s3_key2)

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


# ==================================================================================
# Function: send_vtt_file_and_manifest
# Purpose: Helper function that sends a WebVTT file and Manifest.
# Parameters:
#               child_name - name of the child manifest
#               child_manifest - string that contains the child video manifest
# ==================================================================================
def custom_labels(child_name, child_manifest, pipe_number):
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

    ts_file_path = download_file_from_s3(base_name + ts_segment_name, BUCKET_NAME)

    print("TRANSCRIBE: Getting text from transcribe ")
    # Use TS with FFMPEG to make captions
    text = prepare_analyze_video(ts_file_path)

    try:
        os.remove(ts_file_path)
    except Exception as e:
        print("TS file was not there " + ts_file_path)

    return True


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
        # It is a master manifest. Do nothing.
        print("It is a master manifest. Do nothing.")

    # Check if the file is a child manifest file.
    elif '.m3u8' in s3_key:
        # Check to see if it is the _416x234_200k rendition of the video. This is what I will use for
        # custom label rekognition.
        if NAME_MODIFIER in s3_key:
            # Get child manifest
            print("DEBUG: Get child manifest, s3_key" + s3_key)
            manifest_file = get_s3_file_versionid(s3_key, s3_version)
            # Get child name
            manifest_name = s3_key.split('/')[-1]

            custom_labels(manifest_name, manifest_file, pipe_number)
            print("caption done")
    print("all done")
    return True


def main():
    pass


if __name__ == '__main__':
    main()
