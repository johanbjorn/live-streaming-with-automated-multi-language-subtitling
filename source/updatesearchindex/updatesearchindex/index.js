var AWS = require("aws-sdk");

exports.handler = (event, context, callback) => {
    // TODO implement
    //let xx = JSON.parse(event)
      const { body } = event.Records[0];
      console.log(body);

  
      let message = JSON.parse(JSON.parse(body).Message)
      let jobId = message.JobId
      let status = message.Status
      let api = message.API
      console.log("DEBUG, handler, api: " + api);
      let offset = message.Video.S3ObjectName.substr(27, 5) * 6006
      console.log("JobId: " + jobId);
      console.log("Status: "+ status);
      var params = {
        JobId: jobId, /* required */
      };
      console.log("params.JobId: " + params.JobId);
    //** get mp3 file name : Video.S3ObjectName see https://docs.aws.amazon.com/rekognition/latest/dg/api-video.html
    var rekognition = new AWS.Rekognition();
    rekognition.getCelebrityRecognition(params, function(err, data) {
      if (err) {
          console.log("rekognition if (err) ");
          console.log(err, err.stack);
      }else {
        console.log("rekognition else 1");
        console.log(data); 
        console.log("rekognition else 2");
        //let datap = JSON.parse(data)
        data.Celebrities.forEach(label => {
            //console.log(label);
            console.log("data.Labels.forEac 1"  );
            label.Timestamp = label.Timestamp + offset
            console.log("data.Labels.forEac 2"  );
            indexDocument(label, api)
            console.log("data.Labels.forEac 3"  );
          });
      }
    });    
  
////********
    callback();
};

function indexDocument(json, api) {
    console.log("indexDocument 1"  );
    var region = process.env.REGION; // e.g. us-west-1
    var domain = process.env.DOMAIN; // e.g. search-domain.region.es.amazonaws.com //'/' + id;
    var index = "celebrity-detect"
    console.log("DEBUG, indexDocument, api: " + api);
    if(api=="StartLabelDetection"){
      console.log("DEBUG, indexDocument, if api==Star..");
      index = 'label-detect';      
    }
    console.log('Debug, using index: ' + index);
    var type = '_doc';
    
    var endpoint = new AWS.Endpoint(domain);
    var request = new AWS.HttpRequest(endpoint, region);
    
    request.method = 'POST';
    request.path += index + '/' + type 
    request.body = JSON.stringify(json);
    request.headers['host'] = domain;
    request.headers['Content-Type'] = 'application/json';
    // Content-Length is only needed for DELETE requests that include a request
    // body, but including it for all requests doesn't seem to hurt anything.
    request.headers['Content-Length'] = Buffer.byteLength(request.body);
    
    var credentials = new AWS.EnvironmentCredentials('AWS');
    var signer = new AWS.Signers.V4(request, 'es');
    signer.addAuthorization(credentials, new Date());
    
    var client = new AWS.HttpClient();
    client.handleRequest(request, null, function(response) {
        console.log(response.statusCode + ' ' + response.statusMessage);
        var responseBody = '';
        response.on('data', function (chunk) {
          responseBody += chunk;
        });
        response.on('end', function (chunk) {
          console.log('Response body: ' + responseBody);
        });
    }, function(error) {
    console.log('Error: ' + error);
    });
}