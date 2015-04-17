// Start polling for preview and full render job status and take action when document is ready
$(document).ready(function(){
    // Poll for preview image
    $(".js-nopreview").each(function(){
        var jobId = this.id;
        var intervalTime = 1000;
        var intervalID = setInterval(function poll(){
            $.ajax({
                url: "/preview_poll",
                data: {'jobid': jobId},
                dataType: "json"
            }).done(function(json){
                var info = json.job_info;
                var newid = '#'.concat(jobId);
                if(info.jobstatus != 'Done' && info.jobstatus != 'Failed'){
                    // Display loading gif.
                    $(newid).html(
                        "<div class='loading'><img src='/static/img/loading.gif'></div>");
                }else{
                    if(info.jobstatus != 'Failed'){
                        // Stop polling on success
                        $(newid).html(
                            "<a href="  + info.renderurl + ">" +
                            "<img src=" + info.renderurl + ">" +
                            "</a>");
                        clearInterval(intervalID);
                    }else{
                        // Stop polling on failure
                        $(newid).html(
                            "<p><strong class='red'>Preview Failure</strong></p>");
                        clearInterval(intervalID);
                    }
                }
            });
        }, intervalTime);
    });
    
    // Poll for full render job status
    $(".js-nofull").each(function(){
        var jobId = this.id;
        var intervalTime = 10000;
        if(jobId){
            var intervalID = setInterval(function poll(){
                $.ajax({
                    url: "/status_poll",
                    data: {'jobid': jobId},
                    dataType: "json"
                }).done(function(json){
                    var info = json.job_info;
                    var newid = '#'.concat(jobId);
                    if(info.jobstatus != 'Done' && info.jobstatus != 'Failed'){
                        // Update status and elapsed time.
                        $(newid).find("#js-fullstatus").html(info.jobstatus);
                    }else{
                        if(info.jobstatus != 'Failed'){
                            // Stop polling on success
                            $(newid).html(
                                "<a  class='button not-rounded full-width center'" +
                                    "href=" + info.renderurl + ">Download full size image." +
                                "</a>");
                            clearInterval(intervalID);
                        }else{
                            // Stop polling on failure
                            $(newid).html(
                                "<p><strong class='red'>Composite Failure</strong></p>");
                            clearInterval(intervalID);
                        }
                    }
                });
            }, intervalTime);
        }
    });

});

// Stop polling for a preview when 
function stopPreviewPoll(data, intervalID){
    if(data.bool === false){
        clearInterval(intervalID);
    }
}

// Start polliing for preview status
function startPreviewPoll(jobId, intervalID){
    $.ajax({
        url: "/preview_poll", 
        dataType: "json"
    }).done(function(data){
        if(data.bool === false){
            clearInterval(intervalID);
        }
    });
}

// Stop polliing for full render status when
function stopStatusPoll(data, intervalID){
    if(data.bool === false){
        clearInterval(intervalID);
    }
}

// Start polliing for full render status
function startStatusPoll(jobId, intervalID){
    $.ajax({
        url: "/status_poll", 
        dataType: "json"
    }).done(function(data){
        if(data.bool === false){
            clearInterval(intervalID);
        }
    });
}
