var AWS = require("aws-sdk");

exports.handler = (event, context, callback) => {
    // TODO implement
    //let xx = JSON.parse(event)
    //  const { body } = event.Records[0];
    //  console.log(body);
      const { body } = event.Records[0];
      console.log(body);

  
      let message = JSON.parse(JSON.parse(body).Message)
      let jobId = message.JobId
      let status = message.Status
      let api = message.API
      let offset = message.Video.S3ObjectName.substr(27, 5) * 6006
      console.log("JobId: " + jobId);
      console.log("Status: "+ status);
      var params = {
        JobId: jobId, /* required */
      };

    //** get mp3 file name : Video.S3ObjectName see https://docs.aws.amazon.com/rekognition/latest/dg/api-video.html
    
    var params = {
      JobId: jobId, /* required */
    };
    var rekognition = new AWS.Rekognition();
    rekognition.getLabelDetection(params, function(err, data) {
      if (err) {
          console.log(err, err.stack);
      }else {
        console.log(data); 
        //let datap = JSON.parse(data)
        data.Labels.forEach(label => {
            //console.log(label);
            label.Timestamp = label.Timestamp + offset
            indexDocument(label, api)
          });
      }
    });    

////********
    callback();
};

function indexDocument(json, api) {
    var region = process.env.REGION; // e.g. us-west-1
    var domain = process.env.DOMAIN; // e.g. search-domain.region.es.amazonaws.com //'/' + id;
    var index = "celebrity-detect"
    if(api=="StartLabelDetection"){
      index = 'label-detect';      
    }

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