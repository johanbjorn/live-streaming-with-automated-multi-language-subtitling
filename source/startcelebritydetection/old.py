def get_text_from_transcribe(ts_file_path):

    # Check to make sure that TS file exists
    if not os.path.isfile(ts_file_path):
        print("EXCEPTION: ts file doesn't exist to make PCM file for Transcribe : " + ts_file_path)
        sys.exit()

    # Use ffmpeg to create PCM audio file for Transcribe
    output_pcm = TMP_DIR + str(make_random_string()) + '.pcm'
    cmd = './ffmpeg -hide_banner -nostats -loglevel error -y -i ' + ts_file_path + ' -vn -f s16le -acodec pcm_s16le -ac 1 -ar 16000 ' + output_pcm + '  > /dev/null 2>&1 '
    wav_ffmpeg_response = os.popen(cmd).read()

    # After FFMPEG send the file into S3 and generate presigned URL.
    s3_key = 'audio_files/' + output_pcm.split('/')[-1]
    upload_file_s3(output_pcm, s3_key)
    presigned_url = get_presigned_url_s3(s3_key)

    # Remove the file I just uploaded to s3
    os.remove(output_pcm)

    # Use Presigned url with the API for security.
    client = boto3.client('lambda') 
    try:
        response = client.invoke(FunctionName=TRANSCRIBE_LAMBDA_ARN, Payload=json.dumps({'body' : presigned_url}))
        json_res = json.loads(json.loads(response['Payload'].read())['body'])
    
        # Get Text
        text = json_res['transcript']
        print("DEBUG: Text returned from Transcribe Streaming is: " + text)

    except Exception as e:
        print("EXCEPTION: AWS Transcribe Streaming is throttling! Putting empty subtitle into stream. Increase Transcribe Streaming Limits: " + str(e))
        # Set the text to nothing. 
        text = ""

    return text