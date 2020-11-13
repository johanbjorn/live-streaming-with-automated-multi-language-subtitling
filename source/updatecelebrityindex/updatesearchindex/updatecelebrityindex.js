var AWS = require("aws-sdk");

exports.handler = (event, context, callback) => {

  const { body } = event.Records[0];
  console.log(body);

  let message = JSON.parse(JSON.parse(body).Message)

  let jobId = message.JobId
  let status = message.Status
  let responseTimestamp = new Date(message.Timestamp)
  let api = message.API

  var first = message.Video.S3ObjectName.lastIndexOf("_");
  var last = message.Video.S3ObjectName.indexOf(".");
  var segmentNumber = parseInt(message.Video.S3ObjectName.substring(first + 1, last)) - 1;
  
  let offset = segmentNumber * process.env.SEGMENTLENGTH

  var params = {
    JobId: jobId,
  };
  console.log("params.JobId: " + params.JobId);
  var rekognition = new AWS.Rekognition({ region: process.env.REGION });
  rekognition.getCelebrityRecognition(params, function(err, data) {
    if (err) {
      console.log(err, err.stack);
    }
    else {
      let map = new Map(); // to ensure that same celeb in same 6 second segement is not included multple times
      data.Celebrities.forEach(label => {
        var includeonly = process.env.ONLYINCLUDE.split(",") // only include celebs we are actually interesed in 

        //if (includeonly.includes(label.Celebrity.Name)) {
          // creating multiple links as starting time for live stream is not always clear
          for (var i = -3; i < 6; i++) {
            var add = i * process.env.SEGMENTLENGTH;
            var stopWatchSeconds = offset - process.env.STOPWATCHOFFSET
            label.StopWatch = new Date(stopWatchSeconds).toISOString().substr(11, 8) // approximation of left corner stopwatch

            label.Timestamp = offset + add
            label.mp4File = message.Video.S3ObjectName

            var startEnd = toStartEndTime(process.env.CHANNELSTARTTIME, parseInt(label.Timestamp))
            var complUrl = process.env.URL + "?start=" + startEnd.startTime + "&end=" + startEnd.endTime
            console.log("complUrl: " + complUrl);

            label["Link" + i] = complUrl;
            label["ReponseTimestamp"] = responseTimestamp;
          }

          if (!map.has(label.Celebrity.Name)) {
            label.cause = "undefined";
            indexDocument(label, api, 7);
            map.set(label.Celebrity.Name, label.mp4File)
          }
        //}
      });
    }
  });
  callback();
};

function indexDocument(json, api, number) {
  var region = process.env.REGION;
  var domain = process.env.DOMAIN;


  var index = "celebrity-detect-" + number;
  var type = '_doc';

  var endpoint = new AWS.Endpoint(domain);
  var request = new AWS.HttpRequest(endpoint, region);

  request.method = 'POST';
  request.path += index + '/' + type
  request.body = JSON.stringify(json);
  request.headers['host'] = domain;
  request.headers['Content-Type'] = 'application/json';
  request.headers['Content-Length'] = Buffer.byteLength(request.body);

  var credentials = new AWS.EnvironmentCredentials('AWS');
  var signer = new AWS.Signers.V4(request, 'es');
  signer.addAuthorization(credentials, new Date());

  var client = new AWS.HttpClient();
  client.handleRequest(request, null, function(response) {
    console.log(response.statusCode + ' ' + response.statusMessage);
    var responseBody = '';
    response.on('data', function(chunk) {
      responseBody += chunk;
    });
    response.on('end', function(chunk) {
      console.log('Response body: ' + responseBody);
    });
  }, function(error) {
    console.log('Error: ' + error);
  });
}

function toStartEndTime(channelStartTime, seconds) {
  var offset = new Date(seconds).toISOString().substr(11, 8)
  var startTime = new Date(channelStartTime)

  var str = offset.toString()
  var first = str.indexOf(":");
  var last = str.lastIndexOf(":");
  var hour = parseInt(str.substr(0, first));
  var min = parseInt(str.substring(first + 1, last));
  var sec = parseInt(str.substring(last + 1));

  startTime.setMonth(startTime.getMonth() + 1)
  startTime.setHours(startTime.getHours() + hour)
  startTime.setMinutes(startTime.getMinutes() + min)
  startTime.setSeconds(startTime.getSeconds() + sec)
  
  var start = startTime.getFullYear() + "-" + startTime.getMonth() + "-" + startTime.getDate() + "T" + startTime.getHours() + ":" + startTime.getMinutes() + ":" + startTime.getSeconds()
  startTime.setSeconds(startTime.getSeconds() + parseInt(process.env.INTERVALSTARTEND))
  var end = startTime.getFullYear() + "-" + startTime.getMonth() + "-" + startTime.getDate() + "T" + startTime.getHours() + ":" + startTime.getMinutes() + ":" + startTime.getSeconds()
  
  return { "startTime": start, "endTime": end }
}