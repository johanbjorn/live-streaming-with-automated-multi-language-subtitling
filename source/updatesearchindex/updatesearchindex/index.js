var AWS = require("aws-sdk");

exports.handler = (event, context, callback) => {
    // TODO implement
    //let xx = JSON.parse(event)
    event.Records.forEach(record => {
        const { body } = record;
        console.log(body);
  
    
        let message = JSON.parse(JSON.parse(body).Message)
        let jobId = message.JobId
        let status = message.Status
        console.log("JobId: " + jobId);
        console.log("Status: "+ status);
        var params = {
          JobId: jobId, /* required */
        };
        var rekognition = new AWS.Rekognition();
        rekognition.getLabelDetection(params, function(err, data) {
          if (err) console.log(err, err.stack); // an error occurred
          else     console.log(data);           // successful response
        });
        
    });
    
    
    
    callback();
};
