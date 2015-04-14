import os
import operator
import itertools
from datetime import datetime
from models import Paths, PathRow, UserJob, RenderCache
from pyramid.view import view_config
from pyramid.httpexceptions import HTTPFound
from sqs import make_SQS_connection, get_queue, build_job_message, send_message
from collections import OrderedDict
import pyramid.httpexceptions as exc


# Define AWS credentials
AWS_ACCESS_KEY_ID = os.environ['AWS_ACCESS_KEY_ID']
AWS_SECRET_ACCESS_KEY = os.environ['AWS_SECRET_ACCESS_KEY']
REGION = 'us-west-2'

# Requests are passed into appropriate queues, as defined here.

COMPOSITE_QUEUE = 'snapsat_composite_queue'
PREVIEW_QUEUE = 'snapsat_preview_queue'


"""
Helper functions:
1. add_to_queue - Adds a request to the appropriate queue.

Views available:
1. landing - Landing page.
2. create - Allow a user to define their area of interest.
3. request_scene - Requests both the full and preview renders.
4. request_preview - Requests just the preview render.
5. scene_status - Given a scene ID display available data.
6. ajax - Returns a dictionary with all available scenes.
"""


@view_config(route_name='landing', renderer='templates/landing.jinja2')
def landing(request):
    """
    Landing page.
    No context is passed in, the page is purely static.
    """
    return {}


@view_config(route_name='guide', renderer='templates/guide.jinja2')
def guide(request):
    """
    Guide page.
    """
    return {}


@view_config(route_name='create', renderer='templates/create.jinja2')
def create(request):
    """
    Create page.
    Allows a user to define their area of interest and receive appropriate
    lists of scenes for it.
    """
    return scene_options_ajax(request)


def add_to_queue_composite(request):
    """
    Helper method for adding request to queue and adding to db.
    """
    band1 = request.params.get('band1')
    band2 = request.params.get('band2')
    band3 = request.params.get('band3')
    scene_id = request.matchdict['scene_id']

    if not RenderCache.full_render_availability(scene_id, band1, band2, band3):
        SQSconn = make_SQS_connection(REGION,
                                      AWS_ACCESS_KEY_ID,
                                      AWS_SECRET_ACCESS_KEY)
        current_queue = get_queue(SQSconn, COMPOSITE_QUEUE)
        jobid = UserJob.new_job(entityid=scene_id,
                                band1=band1, band2=band2, band3=band3,
                                rendertype=u'full')
        message = build_job_message(job_id=jobid,
                                    email='test@test.com',
                                    scene_id=scene_id,
                                    band_1=band1, band_2=band2, band_3=band3)
        send_message(SQSconn,
                     current_queue,
                     message['body'],
                     message['attributes'])


def add_to_queue_preview(request):
    """
    Helper method for adding request to queue and adding to db.
    """
    band1 = request.params.get('band1')
    band2 = request.params.get('band2')
    band3 = request.params.get('band3')
    scene_id = request.matchdict['scene_id']

    if not RenderCache.preview_render_availability(
            scene_id,
            band1, band2, band3):

        SQSconn = make_SQS_connection(REGION,
                                      AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)

        current_queue = get_queue(SQSconn, PREVIEW_QUEUE)

        jobid = UserJob.new_job(entityid=scene_id,
                                band1=band1, band2=band2, band3=band3,
                                rendertype=u'preview')

        message = build_job_message(job_id=jobid,
                                    email='test@test.com',
                                    scene_id=scene_id,
                                    band_1=band1, band_2=band2, band_3=band3)

        send_message(SQSconn,
                     current_queue,
                     message['body'], message['attributes'])


@view_config(route_name='request_composite', renderer='json')
def request_composite(request):
    """
    Request both the preview and fullsize images for a particular composite.
    Redirect to scene page and goto band requested.
    If incorrect band combo is requested, bad request.

    """
    # Add full render and preview job to apprpriate queues
    if valid_band_combo(request):
        bands = (request.params.get('band1') + request.params.get('band2') +
                 request.params.get('band3'))
        add_to_queue_composite(request)
        add_to_queue_preview(request)
        return HTTPFound(location='/scene/{}#{}'.format(
            request.matchdict['scene_id'], bands))
    else:
        raise exc.HTTPBadRequest()


@view_config(route_name='request_preview', renderer='json')
def request_preview(request):
    """
    Request the preview image for a particular composite.
    Redirect to scene page and goto band requested.
    If incorrect band combo is requested, bad request.
    """
    if valid_band_combo(request):
        # Add preview render job to apprpriate queues
        bands = (request.params.get('band1') + request.params.get('band2') +
                 request.params.get('band3'))
        add_to_queue_preview(request)
        return HTTPFound(location='/scene/{}#{}'.format(
            request.matchdict['scene_id'], bands))
    else:
        raise exc.HTTPBadRequest()


def valid_band_combo(request):
    """
    Return true if band combo is valid, False if not.
    """
    valid = [1, 2, 3, 4, 5, 6, 7, 9]
    bands = [int(request.params.get('band1')),
             int(request.params.get('band2')),
             int(request.params.get('band3'))]
    # Check if all bands are unique
    unique = len(bands) == len(set(bands))
    return all(x in valid for x in bands) and unique


@view_config(route_name='scene', renderer='templates/scene.jinja2')
def scene(request):
    """
    Given sceneID display available previews, rendered photos/links, status of
    jobs in process.
    """

    # Get scene id and list of rendered or rendering previews and full
    # composities from the render_cache table
    scene_id = request.matchdict['scene_id']
    rendered_rendering_composites = RenderCache.get_rendered_rendering(scene_id)

    # Initialize composties dictionary
    composites = {}

    # Populate composites dictionary with one dictionary per band combination
    if rendered_rendering_composites:
        # Loop through list of rendered or rendering composites
        for composite in rendered_rendering_composites:
            # Get band combination and create string for dictionary key
            band_combo = '{}{}{}'.format(composite.band1,
                                         composite.band2,
                                         composite.band3)
            # If band combination dictionary is not in composites dictionary,
            # add it and initialize it with band values
            if band_combo not in composites:
                composites.update({band_combo: {'band1': composite.band1,
                                                'band2': composite.band2,
                                                'band3': composite.band3}})

            # For full render of a band combination that is currently being
            # rendered update dictionary with status and elapsed time.
            if composite.currentlyrend and composite.rendertype == u'full':
                job_status, start_time, last_modified = (
                    UserJob.job_status_and_times(composite.jobid))
                elapsed_time = str(datetime.utcnow() - start_time)
                composites[band_combo].update({'fulljobid': composite.jobid,
                                               'fullurl': False,
                                               'fullstatus': job_status,
                                               'elapsedtime': elapsed_time})

            # For preview render of a band combination that is currently being
            # rendered update dictionary with status.
            if composite.currentlyrend and composite.rendertype == u'preview':
                job_status = UserJob.job_status(composite.jobid)
                composites[band_combo].update({'previewjobid': composite.jobid,
                                               'previewurl': False,
                                               'previewstatus': job_status})

            # For full render of a band combination that has been rendered,
            # update dictionary with status and elapsed time.
            if not composite.currentlyrend and composite.rendertype == u'full':
                job_status, start_time, last_modified = (
                    UserJob.job_status_and_times(composite.jobid))
                elapsed_time = str(datetime.utcnow() - start_time)
                composites[band_combo].update({'fulljobid': composite.jobid,
                                               'fullurl': composite.renderurl,
                                               'fullstatus': job_status,
                                               'elapsedtime': elapsed_time})

            # For preview render of a band combination that has been rendered,
            # update dictionary with status.
            if not composite.currentlyrend and composite.rendertype == u'preview':
                job_status = UserJob.job_status(composite.jobid)
                composites[band_combo].update({'previewjobid': composite.jobid,
                                               'previewurl': composite.renderurl,
                                               'previewstatus': job_status})

    # Order composites by band combination.
    composites = OrderedDict(sorted(composites.items()))

    # Get scene metadata from path_row table
    meta_data_list = PathRow.meta_data(scene_id)
    meta_data = {'scene_id': scene_id,
                 'acquisitiondate':
                 meta_data_list[0].strftime('%Y/%m/%d %H:%M:%S'),
                 'cloudcover': meta_data_list[1],
                 'path': meta_data_list[2],
                 'row': meta_data_list[3],
                 'min_lat': meta_data_list[4],
                 'min_lon': meta_data_list[5],
                 'max_lat': meta_data_list[6],
                 'max_lon': meta_data_list[7],
                 'overview_url':
                 meta_data_list[8][0:-10]+scene_id+'_thumb_small.jpg'}

    return {'meta_data': meta_data, 'composites': composites}


@view_config(route_name='scene_options_ajax', renderer='json')
def scene_options_ajax(request):
    """
    Returns a dictionary with all available scenes around the map's center.
    """
    # Lat/lng values default to Seattle, otherwise from Leaflet .getcenter().
    lat = float(request.params.get('lat', 47.614848))
    lng = float(request.params.get('lng', -122.3359059))

    # Filter all available scenes to those which encompass the
    # lat/lng provided from the user. Then, populate a list with
    # the information relevant to our view.
    path_row_list = Paths.pathandrow(lat, lng)

    # Check for zero length path row list to prevent return of all path row
    # combinations n ithe world.
    if not path_row_list:
        return {'scenes': []}

    scenes = PathRow.scenelist(path_row_list)

    sceneList = []
    for i, scene in enumerate(scenes):
        sceneList.append({
            'acquisitiondate': scene.acquisitiondate.strftime('%Y %m %d'),
            'cloudcover': scene.cloudcover,
            'download_url': scene.download_url,
            'entityid': scene.entityid,
            'sliced': scene.entityid[3:9],
            'path': scene.path,
            'row': scene.row})

    # This line may not be necessary.
    sort = sorted(sceneList, key=operator.itemgetter('sliced'), reverse=False)

    # Sort the available scenes based on their Path, then Row.
    outputList = []
    for key, items in itertools.groupby(sort, operator.itemgetter('sliced')):
        outputList.append(list(items))

    # Sort the vailable scenes in each group by date in reverse.
    for group in outputList:
        group.sort(key=operator.itemgetter('acquisitiondate'), reverse=True)

    return {'scenes': outputList}


@view_config(route_name='status_poll', renderer='json')
def status_poll(request):
    """
    Poll database for full render job status.
    """

    # Get jobid from request
    jobid = request.params.get('jobid')
    # Query the database for job status, start time, last modified time
    job_status, start_time, last_modified = (
        UserJob.job_status_and_times(jobid))
    # Calcuate elapsed time
    elapsed_time = str(datetime.utcnow() - start_time)

    # Get render url when job is done
    if job_status == 'Done':
        render_url = RenderCache.get_renderurl(jobid)
    else:
        render_url = None

    # Create job info json output
    job_info = {'jobstatus': job_status,
                'elapsedtime': elapsed_time,
                'renderurl': render_url}

    return {'job_info': job_info}


@view_config(route_name='preview_poll', renderer='json')
def preview_poll(request):
    """
    Poll database for preview render job status.
    """

    # Get jobid from request
    jobid = request.params.get('jobid')
    # Query the database for job status
    job_status = UserJob.job_status(jobid)

    # Get render url when job is done
    if job_status == 'Done':
        render_url = RenderCache.get_renderurl(jobid)
    else:
        render_url = None

    # Create job info json output
    job_info = {'jobstatus': job_status,
                'renderurl': render_url}

    return {'job_info': job_info}
