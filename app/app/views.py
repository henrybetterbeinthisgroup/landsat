import os
import operator
import itertools
from datetime import datetime
from models import Paths, PathRow, UserJob, RenderCache
from pyramid.view import view_config
from pyramid.httpexceptions import HTTPFound
from sqs import make_SQS_connection, get_queue, build_job_message, send_message

# Define AWS credentials
AWS_ACCESS_KEY_ID = os.environ['AWS_ACCESS_KEY_ID']
AWS_SECRET_ACCESS_KEY = os.environ['AWS_SECRET_ACCESS_KEY']
REGION = 'us-west-2'

# Requests are passed into appropriate queues, as defined here.
RENDER_QUEUE = 'snapsat_render_queue'
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


@view_config(route_name='create', renderer='templates/create.jinja2')
def create(request):
    """
    Create page.
    Allows a user to define their area of interest and receive appropriate
    lists of scenes for it.
    """
    return scene_options_ajax(request)


def add_to_queue_full(request):
    """
    Helper method for adding request to queue and adding to db.
    """
    band1 = request.params.get('band_combo')[0]
    band2 = request.params.get('band_combo')[1]
    band3 = request.params.get('band_combo')[2]
    scene_id = request.matchdict['scene_id']

    if not RenderCache.full_render_availability(scene_id, band1, band2, band3):
        SQSconn = make_SQS_connection(REGION,
                                      AWS_ACCESS_KEY_ID,
                                      AWS_SECRET_ACCESS_KEY)
        current_queue = get_queue(SQSconn, RENDER_QUEUE)
        jobid = UserJob.new_job(entityid=scene_id,
                                band1=band1,
                                band2=band2,
                                band3=band3
                                )
        message = build_job_message(job_id=jobid,
                                    email='test@test.com',
                                    scene_id=scene_id,
                                    band_1=band1,
                                    band_2=band2,
                                    band_3=band3
                                    )
        send_message(SQSconn,
                     current_queue,
                     message['body'],
                     message['attributes'])

    return jobid


def add_to_queue_preview(request):
    """
    Helper method for adding request to queue and adding to db.
    """
    band1 = request.params.get('band_combo')[0]
    band2 = request.params.get('band_combo')[1]
    band3 = request.params.get('band_combo')[2]
    scene_id = request.matchdict['scene_id']
    if not RenderCache.preview_render_availability(
            scene_id,
            band1, band2, band3):

        SQSconn = make_SQS_connection(
                REGION, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)

        current_queue = get_queue(SQSconn, PREVIEW_QUEUE)

        message = build_job_message(
                job_id=0,
                email='test@test.com',
                scene_id=scene_id,
                band_1=band1, band_2=band2, band_3=band3)

        send_message(SQSconn,
                     current_queue,
                     message['body'], message['attributes'])

        print 'successfully added to preview queue'


@view_config(route_name='request_scene', renderer='json')
def request_scene(request):
    """
    Request both the preview and fullsize images for a particular composite.
    """
    jobid = add_to_queue_full(request)
    return HTTPFound(location='/scene/{}'.format(
        request.matchdict['scene_id']))


@view_config(route_name='request_preview', renderer='json')
def request_preview(request):
    """
    Request the preview image for a particular composite.
    """
    add_to_queue_preview(request)
    return HTTPFound(location='/scene/{}'.format(
        request.matchdict['scene_id']))


@view_config(route_name='scene_page', renderer='templates/scene.jinja2')
def scene_page(request):
    """
    Given sceneID display available previews, rendered photos/links, status of
    jobs in process.
    """

    scene_id = request.matchdict['scene_id']
    rendered_rendering_composites = RenderCache.get_rendered_rendering(
        scene_id)
    rendered_composites = []
    rendering_composites = {}
    for composite in rendered_rendering_composites:
        if composite.currentlyrend:
            rendering_composites.append(composite)
            job_status, start_time, last_modified = (
                UserJob.job_status_and_times(composite.jobid))
            elapsed_time = str(datetime.utcnow() - start_time)
            rendering_composites[
                composite.jobid] = ({'status': job_status,
                                     'starttime': start_time,
                                     'lastmodified': last_modified,
                                     'elapsedtime': elapsed_time,
                                     'band1': composite.band1,
                                     'band2': composite.band2,
                                     'band3': composite.band3})
        else:
            rendered_composites.append(composite)

    return {'scene_id': scene_id,
            'rendered_composites': rendered_composites,
            'rendering_composites': rendering_composites,
            }


@view_config(route_name='scene_options_ajax', renderer='json')
def scene_options_ajax(request):
    """
    Returns a dictionary with all available scenes around the map's center.
    """

    def sceneList(request):
        """
        Returns a dictionary with all available scenes around the map's center.
        """
        # Lat/lng values default to Seattle, otherwise from Leaflet .getcenter().
        lat = float(request.params.get('lat', 47.614848))
        lng = float(request.params.get('lng', -122.3359059))

        # Filter all available scenes to those which encompass the
        # lat/lng provided from the user. Then, populate a list with
        # the information relevant to our view.
        scenes = PathRow.scenelist(Paths.pathandrow(lat, lng))
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

        return {'scenes': outputList}


@view_config(route_name='status_poll', renderer='json')
def status_poll(request):
    """
    Poll database for render job status.
    """
    jobid = request.params.get('jobid')
    job_info = UserJob.job_status_and_times(jobid)

    return {'job_info': job_info}
