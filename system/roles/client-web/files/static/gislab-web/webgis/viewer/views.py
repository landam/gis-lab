# -*- coding: utf-8 -*-

import re
import json
import os.path
import urllib
import urllib2
import hashlib
import time
import datetime
import contextlib
from urlparse import parse_qs, urlsplit, urlunsplit
import xml.etree.ElementTree as etree

from django.conf import settings
from django.core.cache import cache
from django.shortcuts import render
from django.http import HttpResponse, Http404, HttpResponseRedirect
from django.core.urlresolvers import reverse
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.utils.translation import ugettext as _

from webgis.viewer import forms
from webgis.viewer import models
from webgis.viewer.metadata_parser import MetadataParser
from webgis.libs.auth.decorators import basic_authentication
from webgis.mapcache import get_tile_response, get_legendgraphic_response, WmsLayer, TileNotFoundException


OSM_LAYER = {'name': 'OSM', 'type': 'OSM', 'title': 'Open Street Map'}

GOOGLE_LAYERS = {
	'GHYBRID': {'name': 'GHYBRID', 'type': 'google', 'title': 'Google Hybrid'},
	'GROADMAP': {'name': 'GROADMAP', 'type': 'google', 'title': 'Google Roadmap'},
	'GSATELLITE': {'name': 'GSATELLITE', 'type': 'google', 'title': 'Google Satellite'},
	'GTERRAIN': {'name': 'GTERRAIN', 'type': 'google', 'title': 'Google Terrain'},
}

GISLAB_VERSION = {}
try:
	with open('/etc/gislab_version', 'r') as f:
		param_pattern = re.compile('\s*(\w+)\s*\=\s*"([^"]*)"')
		for line in f:
			match = param_pattern.match(line)
			if match:
				name, value = match.groups()
				GISLAB_VERSION[name] = value
except IOError:
	pass


def _get_tile_resolutions(scales, units, dpi=96):
	"""Helper function to compute OpenLayers tile resolutions."""

	dpi = float(dpi)
	factor = {'ft': 12.0, 'm': 39.3701, 'mi': 63360.0, 'dd': 4374754.0}

	inches = 1.0 / dpi
	monitor_l = inches / factor[units]

	resolutions = []
	for m in scales:
		resolutions.append(monitor_l * int(m))
	return resolutions

def secure_url(request, location=None):
	return request.build_absolute_uri(location).replace('http:', 'https:')

def set_query_parameters(url, params_dict):
	"""Given a URL, set or replace a query parameters and return the
	modified URL. Parameters are case insensitive.

	>>> set_query_parameters('http://example.com?foo=bar&biz=baz', {'foo': 'stuff'})
	'http://example.com?foo=stuff&biz=baz'

	"""
	url_parts = list(urlsplit(url))
	query_params = parse_qs(url_parts[3])

	params = dict(params_dict)
	new_params_names = [name.lower() for name in params_dict.iterkeys()]
	for name, value in query_params.iteritems():
		if name.lower() not in new_params_names:
			params[name] = value

	url_parts[3] = urllib.urlencode(params, doseq=True)
	return urlunsplit(url_parts)

def clean_project_name(project):
	"""Returns project name without QGIS file extension ('.qgs')"""
	if project.lower().endswith(".qgs"):
		return os.path.splitext(project)[0]
	return project

def store_project_layers_info(project_key, publish, extent, resolutions, projection):
	prefix = "{0}:{1}:".format(project_key, publish)
	cache.set_many({
		prefix+'extent': ','.join(map(str, extent)),
		prefix+'resolutions': ','.join(map(str, resolutions)),
		prefix+'projection': projection
	})

def get_project_layers_info(project_key, publish, project=None):
	prefix = "{0}:{1}:".format(project_key, publish)
	data = cache.get_many((prefix+'extent', prefix+'resolutions', prefix+'projection'))
	if data:
		return { param.replace(prefix, ''): value for param, value in data.iteritems() }
	elif project:
		metadata_filename = os.path.join(settings.GISLAB_WEB_PROJECT_ROOT, clean_project_name(project) + '.meta')
		try:
			metadata = MetadataParser(metadata_filename)
			if int(metadata.publish_date_unix) == int(publish):
				store_project_layers_info(project_key, publish, metadata.extent, metadata.tile_resolutions, metadata.projection['code'])
				return {
					'extent': metadata.extent,
					'resolutions': metadata.tile_resolutions,
					'projection': metadata.projection['code']
				}
		except Exception, e:
			pass
	return {}

def get_last_project_version(project):
	full_project = os.path.join(settings.GISLAB_WEB_PROJECT_ROOT, project)
	project = clean_project_name(project)
	project_pattern = re.compile(re.escape(os.path.basename(project))+'_(\d{10})\.qgs')
	matched_project_versions = []
	for filename in os.listdir(os.path.dirname(full_project)):
		match = project_pattern.match(filename)
		if match:
			matched_project_versions.append((int(match.group(1)), filename))
	if matched_project_versions:
		# load last published project file
		project_filename = sorted(matched_project_versions, reverse=True)[0][1]
		project_filename = os.path.join(os.path.dirname(project), project_filename)
		return clean_project_name(project_filename)
	return project

@basic_authentication(realm="OWS API")
def ows_request(request):
	url = "{0}?{1}".format(settings.GISLAB_WEB_MAPSERVER_URL.rstrip("/"), request.environ['QUERY_STRING'])
	owsrequest = urllib2.Request(url)
	owsrequest.add_header("User-Agent", "GIS.lab Web")
	with contextlib.closing(urllib2.urlopen(owsrequest)) as resp:
		resp_content = resp.read()
		content_type = resp.info().getheader('Content-Type')
		status = resp.getcode()
		return HttpResponse(resp_content, content_type=content_type, status=status)


@login_required
def tile(request, project_hash, publish, layers_hash=None, z=None, x=None, y=None, format=None):
	params = {key.upper(): request.GET[key] for key in request.GET.iterkeys()}
	project = params['PROJECT']+'.qgs'
	layer_params = get_project_layers_info(project_hash, publish, project=project)
	try:
		layer = WmsLayer(
			project=project_hash,
			publish=publish,
			name=layers_hash,
			provider_layers=params['LAYERS'].encode("utf-8"),
			provider_url=set_query_parameters(settings.GISLAB_WEB_MAPSERVER_URL, {'MAP': project}),
			image_format=format,
			tile_size=256,
			metasize=5,
			**layer_params
		)
		return get_tile_response(layer, z=z, x=x, y=y)
	except TileNotFoundException, e:
		raise Http404

@login_required
def legend(request, project_hash, publish, layer_hash=None, zoom=None, format=None):
	params = {key.upper(): request.GET[key] for key in request.GET.iterkeys()}
	project = params['PROJECT']+'.qgs'
	try:
		layer = WmsLayer(
			project=project_hash,
			publish=publish,
			name=layer_hash,
			provider_layers=params['LAYER'].encode('utf-8'),
			provider_url=set_query_parameters(settings.GISLAB_WEB_MAPSERVER_URL, {'MAP': project}),
			image_format=format,
		)
		params.pop('PROJECT')
		params.pop('LAYER')
		return get_legendgraphic_response(layer, zoom, **params)
	except:
		raise Http404

def parse_layers_param(layers_string, layers_capabilities):
	tree = {
		'name': '',
		'layers': []
	}
	parts = layers_string.replace(';/', ';//').split(';/')
	for subtree_string in parts:
		location = os.path.dirname(subtree_string)
		parent = tree
		if location != '/':
			for parent_name in location.split('/')[1:]:
				#if 'layers' not in parent:
				#	parent['layers'] = []
				parent_exists = False
				for child in parent['layers']:
					if child['name'] == parent_name:
						parent = child
						parent_exists = True
						break
				if not parent_exists:
					new_parent = {
						'name': parent_name,
						'layers': []
					}
					parent['layers'].append(new_parent)
					parent = new_parent
		layers_string = os.path.basename(subtree_string)
		for layer_string in layers_string.split(';'):
			layer_info = layer_string.split(':')
			layer_name = layer_info[0]
			layer = layers_capabilities.get(layer_name)
			if layer is None:
				if layer_name == 'BLANK':
					continue
				else:
					raise LookupError(layer_name)

			if len(layer_info) > 1:
				layer['visible'] = int(layer_info[1]) == 1
			if len(layer_info) > 2:
				layer['opacity'] = float(layer_info[2])
			parent['layers'].append(layer)
	return tree

@login_required
def vector_layers(request):
	params = {k.upper(): v for k, v in request.GET.iteritems()}
	project = params.get('PROJECT')
	if project:
		project = clean_project_name(project)
		drawing_filename = os.path.join(settings.GISLAB_WEB_PROJECT_ROOT, '{0}.geojson'.format(project))
		if os.path.exists(drawing_filename):
			return HttpResponse(open(drawing_filename, 'r').read(), content_type='application/json')
	raise Http404


def page(request):
	form = forms.ViewerForm(request.GET)
	if not form.is_valid():
		raise Http404

	context = {'dpi': 96}
	project = form.cleaned_data['PROJECT']

	if project:
		ows_project_name = get_last_project_version(project)
		project = clean_project_name(project)
		metadata_filename = os.path.join(settings.GISLAB_WEB_PROJECT_ROOT, ows_project_name + '.meta')
		try:
			metadata = MetadataParser(metadata_filename)
		except:
			return HttpResponse("Error when loading project or project does not exist", content_type='text/plain', status=404)
		if metadata.expiration:
			expiration_date = datetime.datetime.strptime(metadata.expiration, "%d.%m.%Y").date()
			if datetime.date.today() > expiration_date:
				return HttpResponse("Project has reached expiration date.", content_type='text/plain', status=410)

	# Authentication
	if project and type(metadata.authentication) is dict:
		# backward compatibility
		allow_anonymous = metadata.authentication.get('allow_anonymous')
		owner_authentication = False
	else:
		allow_anonymous = metadata.authentication == 'all' if project else True
		owner_authentication = metadata.authentication == 'owner' if project else False

	if not request.user.is_authenticated() and allow_anonymous:
		# login as quest and continue
		user = models.GislabUser.get_guest_user()
		if user:
			login(request, user)
		else:
			return HttpResponse("Anonymous user is not configured", content_type='text/plain', status=500)

	if (not allow_anonymous and (not request.user.is_authenticated() or request.user.is_guest)):
		# redirect to login page
		login_url = secure_url(request, reverse('login'))
		return HttpResponseRedirect(set_query_parameters(login_url, {'next': secure_url(request)}))
	if owner_authentication and not request.user.is_superuser:
		project_owner = project.split('/', 1)[0]
		if project_owner != request.user.username:
			return HttpResponse("You don't have permissions for this project", content_type='text/plain', status=403)
	context['user'] = request.user

	if project:
		ows_url = set_query_parameters(reverse('viewer:owsrequest'), {'MAP': ows_project_name+'.qgs'})
		context['units'] = {'meters': 'm', 'feet': 'ft', 'miles': 'mi', 'degrees': 'dd' }[metadata.units] or 'dd'
		use_mapcache = metadata.use_mapcache
		project_tile_resolutions = metadata.tile_resolutions

		context['projection'] = metadata.projection
		context['tile_resolutions'] = project_tile_resolutions

		# converts tree with layers data into simple dictionary
		def collect_layers_capabilities(layers_data, capabilities=None):
			if capabilities is None:
				capabilities = {}
			for layer_data in layers_data:
				sublayers = layer_data.get('layers')
				if sublayers:
					collect_layers_capabilities(sublayers, capabilities)
				else:
					capabilities[layer_data['name']] = layer_data
			return capabilities

		# BASE LAYERS
		baselayers_tree = None
		base = form.cleaned_data['BASE']
		if base:
			base_layers_capabilities = collect_layers_capabilities(metadata.base_layers)
			try:
				baselayers_tree = parse_layers_param(base, base_layers_capabilities)['layers']
			except LookupError, e:
				return HttpResponse("Unknown base layer: {0}".format(str(e)), content_type='text/plain', status=400)
		else:
			baselayers_tree = metadata.base_layers

		# ensure that a blank base layer is always used
		if not baselayers_tree:
			baselayers_tree = [{'name': 'BLANK', 'type': 'BLANK', 'title': 'Blank Layer', 'resolutions': project_tile_resolutions}]
		context['base_layers'] = json.dumps(baselayers_tree)

		# OVERLAYS LAYERS
		layers = form.cleaned_data['OVERLAY']
		# override layers tree with LAYERS GET parameter if provided
		if layers:
			overlays_capabilities = collect_layers_capabilities(metadata.overlays) if metadata.overlays else {}
			try:
				layers_tree = parse_layers_param(layers, overlays_capabilities)['layers']
			except LookupError, e:
				return HttpResponse("Unknown overlay layer: {0}".format(str(e)), content_type='text/plain', status=400)
		else:
			layers_tree = metadata.overlays
		context['layers'] = json.dumps(layers_tree) if layers_tree else None

		if use_mapcache:
			project_hash = hashlib.md5(project).hexdigest()
			project_layers_info = get_project_layers_info(project_hash, metadata.publish_date_unix)
			if not project_layers_info:
				store_project_layers_info(project_hash, metadata.publish_date_unix, metadata.extent, project_tile_resolutions, metadata.projection['code'])

			mapcache_url = reverse('viewer:tile', kwargs={'project_hash': project_hash, 'publish': metadata.publish_date_unix, 'layers_hash': '__layers__', 'x': 0, 'y': 0, 'z': 0, 'format': 'png'})
			mapcache_url = mapcache_url.split('/__layers__/')[0]+'/'
			context['mapcache_url'] = mapcache_url
			legend_url = reverse('viewer:legend', kwargs={'project_hash': project_hash, 'publish': metadata.publish_date_unix, 'layer_hash': '__layer__', 'zoom': 0, 'format': 'png'})
			legend_url = legend_url.split('/__layer__/')[0]+'/'
			context['legend_url'] = legend_url
		else:
			context['legend_url'] = ows_url

		context.update({
			'project': project,
			'ows_project': ows_project_name,
			'ows_url': ows_url,
			'wms_url': urllib.unquote(secure_url(request, ows_url)),
			'project_extent': metadata.extent,
			'zoom_extent': form.cleaned_data['EXTENT'] or metadata.zoom_extent,
			'print_composers': metadata.composer_templates if not context['user'].is_guest else None,
			'root_title': metadata.title,
			'author': metadata.contact_person,
			'email': metadata.contact_mail,
			'phone': metadata.contact_phone,
			'organization': metadata.contact_organization,
			'abstract': metadata.abstract,
			'online_resource': metadata.online_resource,
			'access_constrains': metadata.access_constrains,
			'fees': metadata.fees,
			'keyword_list': metadata.keyword_list,
			'publish_user': metadata.gislab_user,
			'publish_date': metadata.publish_date,
			'publish_date_unix': int(metadata.publish_date_unix),
			'selection_color': metadata.selection_color[:-2], #strip alpha channel,
			'topics': json.dumps(metadata.topics) if metadata.topics else '',
			'vector_layers': metadata.vector_layers is not None
		})
		if metadata.message:
			valid_until = datetime.datetime.strptime(metadata.message['valid_until'], "%d.%m.%Y").date()
			if datetime.date.today() <= valid_until:
				context['message'] = metadata.message['text'].replace('\n', '<br />')
		project_info = {
			'gislab_version': metadata.gislab_version,
			'gislab_user': metadata.gislab_user,
			'gislab_unique_id': metadata.gislab_unique_id,
			'publish_date': datetime.datetime.fromtimestamp(metadata.publish_date_unix),
			'last_display': datetime.datetime.now()
		}
		# Update projects registry
		try:
			rows = models.Project_registry.objects.filter(project=project).update(**project_info)
			if not rows:
				models.Project_registry(project=project, **project_info).save()
		except:
			raise
	else:
		context.update({
			'project': 'empty',
			'root_title': _('Empty Project'),
			'project_extent': [-20037508.34, -20037508.34, 20037508.34, 20037508.34],
			'projection': {
				'code': 'EPSG:3857',
				'is_geographic': False
			},
			'units': 'm'
		})
		context['zoom_extent'] = form.cleaned_data['EXTENT'] or context['project_extent']
		context['base_layers'] = json.dumps([OSM_LAYER, GOOGLE_LAYERS['GHYBRID']])

	google = False
	if context.get('base_layers'):
		for google_layer_name in GOOGLE_LAYERS.iterkeys():
			if google_layer_name in context['base_layers']:
				google = True
				break
	context['google'] = google
	context['drawings'] = form.cleaned_data['DRAWINGS']

	context['gislab_unique_id'] = GISLAB_VERSION.get('GISLAB_UNIQUE_ID', 'unknown')
	context['gislab_version'] = GISLAB_VERSION.get('GISLAB_VERSION', 'unknown')

	if settings.DEBUG:
		context['debug'] = True
		context['config'] = dict(context)

	return render(request, "viewer/webgis.html", context, content_type="text/html")


def user_projects(request, username):
	if not request.user.is_authenticated() or request.user.is_guest:
		# redirect to login page
		login_url = secure_url(request, reverse('login'))
		return HttpResponseRedirect(set_query_parameters(login_url, {'next': secure_url(request)}))
	if not username:
		redirect_url = secure_url(request, reverse('viewer:user_projects', kwargs={'username': request.user.username}))
		return HttpResponseRedirect(redirect_url)
	if username != request.user.username:
		if not request.user.is_superuser:
			return HttpResponse("Access Denied", content_type='text/plain', status=403)
		else:
			try:
				request.user = models.GislabUser.objects.get(username=username)
			except models.GislabUser.DoesNotExist:
				return HttpResponse("User does not exist.", content_type='text/plain', status=403)

	projects_root = os.path.join(settings.GISLAB_WEB_PROJECT_ROOT, username)
	projects = [{
		'title': _('Empty Project'),
		'url': request.build_absolute_uri('/'),
	}]
	start_index = len(settings.GISLAB_WEB_PROJECT_ROOT)
	for root, dirs, files in os.walk(projects_root):
		if files:
			# analyze project filenames and group different publications of the same project into one record
			projects_files = {}
			project_pattern = re.compile('(.+)_(\d{10})\.qgs')
			for filename in files:
				match = project_pattern.match(filename)
				if match:
					project_name = match.group(1)
					project_timestamp = int(match.group(2))
				elif filename.endswith('.qgs'):
					project_name = filename[:-4]
					project_timestamp = 0
				else:
					continue
				metadata_filename = filename[:-4]+'.meta'
				if metadata_filename in files:
					if project_name not in projects_files:
						projects_files[project_name] = [(project_timestamp, filename)]
					else:
						projects_files[project_name].append((project_timestamp, filename))

			for project_name, info in projects_files.iteritems():
				# select last project version by timestamp
				ows_project = sorted(info, reverse=True)[0][1]

				project_filename = os.path.join(root, project_name)
				ows_project_filename = os.path.join(root, ows_project)
				metadata_filename = clean_project_name(ows_project_filename) + '.meta'
				try:
					metadata = MetadataParser(metadata_filename)
					project = clean_project_name(project_filename[start_index:])
					url = set_query_parameters(secure_url(request, '/'), {'PROJECT': project})
					ows_project = clean_project_name(ows_project_filename[start_index:])
					ows_url = secure_url(request, reverse('viewer:owsrequest'))
					ows_url = set_query_parameters(ows_url, {'MAP': ows_project+'.qgs'})
					authentication = metadata.authentication
					# backward compatibility with older version
					if type(authentication) is dict:
						if authentication.get('allow_anonymous') and not authentication.get('require_superuser'):
							authentication = 'all'
						else:
							authentication = 'authenticated'
					projects.append({
						'title': metadata.title,
						'url': url,
						'project': project,
						'ows_url': ows_url,
						'authentication': authentication,
						'publication_time_unix': int(metadata.publish_date_unix),
						'expiration_time_unix': int(time.mktime(time.strptime(metadata.expiration, "%d.%m.%Y"))) if metadata.expiration else None
					})
				except IOError:
					# metadata file does not exists or not valid
					pass
	context = {
		'username': username,
		'projects': projects,
		'debug': settings.DEBUG
	}
	return render(request, "viewer/user_projects.html", context, content_type="text/html")