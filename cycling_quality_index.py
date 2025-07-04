#---------------------------------------------------------------------------#
#   Cycling Quality Index                                                   #
#   --------------------------------------------------                      #
#   Script for processing OSM data to analyse the cycling quality of ways.  #
#   Download OSM data input from https://overpass-turbo.eu/s/1IDp,          #
#   save it at data/way_import.geojson and run the script.                  #
#                                                                           #
#   > version/date: 2024-04-15                                              #
#---------------------------------------------------------------------------#

import os, sys, processing, math, time, importlib
from os.path import exists
from qgis.core import NULL

#project directory
from console.console import _console
project_dir = os.path.dirname(_console.console.tabEditorWidget.currentWidget().path) + '/'
place_name = "test_ways"
dir_input = project_dir + 'data/test_ways/' + place_name
dir_output = project_dir + 'data/cycling_quality_index' + '-' + place_name
file_format = '.geojson'
multi_input = False #if "True", it's possible to merge different import files stored in the input directory, marked with an ascending number starting with 1 at the end of the filename (e.g. way_import1.geojson, way_import2.geojson etc.) - can be used to process different areas at the same time or to process a larger area that can't be downloaded in one file

if project_dir not in sys.path:
    sys.path.append(project_dir)

import parameter as p
importlib.reload(p)

import definitions as d
importlib.reload(d)

qgis_layers = {}

#TOD= get those from config file:
ALLOWED_BICYCLE_ACCESS = ['yes', 'permissive', 'designated', 'use_sidepath', 'optional_sidepath', 'discouraged']
LINK_ATTRIBUTES = ['footway', 'cycleway', 'path', 'bridleway']
CROSSING_ATTRIBUTES = ['footway', 'cycleway', 'path', 'bridleway']
SHARED_FOOTWAY_HIGHWAYS = ['footway', 'pedestrian', 'bridleway', 'steps']

WAY_TYPES_CYCLEWAY = [
    'cycle path', 'cycle track', 'shared path', 'segregated path', 
    'shared footway', 'crossing', 'link', 'cycle lane (advisory)', 
    'cycle lane (exclusive)', 'cycle lane (protected)', 'cycle lane (central)'
]

ONEWAY_VALUE_LIST = ['yes', 'no', '-1', 'alternating', 'reversible']
SURFACE_CHECK_TYPES = ['segregated path', 'cycle lane (advisory)', 'cycle lane (exclusive)', 'cycle lane (protected)', 'cycle lane (central)']
TRAFFIC_MODES = ['motor_vehicle', 'psv', 'parking']

#list of new attributes, important for calculating cycling quality index
new_attributes_dict = {
        'way_type': 'String',
        'index': 'Int',
        'index_10': 'Int',
        'stress_level': 'Int',
        'offset': 'Double',
        'offset_cycleway_left': 'Double',
        'offset_cycleway_right': 'Double',
        'offset_sidewalk_left': 'Double',
        'offset_sidewalk_right': 'Double',
        'type': 'String',
        'side': 'String',
        'proc_width': 'Double',
        'proc_surface': 'String',
        'proc_smoothness': 'String',
        'proc_oneway': 'String',
        'proc_sidepath': 'String',
        'proc_highway': 'String',
        'proc_maxspeed': 'Int',
        'proc_traffic_mode_left': 'String',
        'proc_traffic_mode_right': 'String',
        'proc_separation_left': 'String',
        'proc_separation_right': 'String',
        'proc_buffer_left': 'Double',
        'proc_buffer_right': 'Double',
        'proc_mandatory': 'String',
        'proc_traffic_sign': 'String',
        'fac_width': 'Double',
        'fac_surface': 'Double',
        'fac_highway': 'Double',
        'fac_maxspeed': 'Double',
        'fac_protection_level': 'Double',
        'prot_level_separation_left': 'Double',
        'prot_level_separation_right': 'Double',
        'prot_level_buffer_left': 'Double',
        'prot_level_buffer_right': 'Double',
        'prot_level_left': 'Double',
        'prot_level_right': 'Double',
        'base_index': 'Int',
        'fac_1': 'Double',
        'fac_2': 'Double',
        'fac_3': 'Double',
        'fac_4': 'Double',
        'data_bonus': 'String',
        'data_malus': 'String',
        'data_incompleteness': 'Double',
        'data_missing': 'String',
        'data_missing_width': 'Int',
        'data_missing_surface': 'Int',
        'data_missing_smoothness': 'Int',
        'data_missing_maxspeed': 'Int',
        'data_missing_parking': 'Int',
        'data_missing_lit': 'Int',
        'filter_usable': 'Int',
        'filter_way_type': 'String'
    }


def check_sidepath(sidepath_dict, id, key, checks):
    for item in sidepath_dict[id][key].keys():
        if checks <= 2:
            if sidepath_dict[id][key][item] == checks:
                return 'yes'
        else:
            if sidepath_dict[id][key][item] >= checks * 0.66:
                return 'yes'
    return 'no'


def print_timestamped_message(message):
    print(time.strftime('%H:%M:%S', time.localtime()), message)


def reproject_layer(input_layer, target_crs):
    print_timestamped_message('Reproject data...')
    return processing.run('native:reprojectlayer', {
        'INPUT': input_layer,
        'TARGET_CRS': QgsCoordinateReferenceSystem(target_crs),
        'OUTPUT': 'memory:'
    })['OUTPUT']


def retain_fields(layer, fields):
    print_timestamped_message('Prepare data...')
    return processing.run('native:retainfields', {
        'INPUT': layer,
        'FIELDS': fields,
        'OUTPUT': 'memory:'
    })['OUTPUT']


def ensure_attributes(layer, attributes_list, new_attributes_dict):
    with edit(layer):
        for attr in attributes_list:
            if layer.fields().indexOf(attr) == -1:
                field_type = new_attributes_dict.get(attr, 'String')
                qvariant_type = {
                    'Double': QVariant.Double,
                    'Int': QVariant.Int,
                    'String': QVariant.String
                }[field_type]
                layer.dataProvider().addAttributes([QgsField(attr, qvariant_type)])
        layer.updateFields()


def determine_maxspeed(feature, hw):
    maxspeed = feature.attribute('maxspeed')
    if maxspeed == 'walk' or (not maxspeed and hw == 'living_street'):
        return 10
    if maxspeed == 'none':
        return 299
    if not maxspeed and hw == 'living_street':
        return 10
    return d.getNumber(maxspeed)


def check_sidepath(sidepath_dict, id, key, checks):
    key_dict = sidepath_dict[id].get(key, {})
    if sum(key_dict.values()) >= (2/3) * checks:
        return 'yes'
    return 'no'


def update_feature_sidepath_status(feature, sidepath_dict, field_ids, highway_class_list):
    id = feature.attribute('id')
    is_sidepath = feature.attribute('is_sidepath')
    checks = sidepath_dict[id].get('checks')
    if feature.attribute('footway') == 'sidewalk':
        is_sidepath = 'yes'
    if not is_sidepath:
        is_sidepath = 'no'
        for key in ['id', 'highway', 'name']:
            is_sidepath = check_sidepath(sidepath_dict, id, key, checks)
            if is_sidepath == 'yes':
                break

    feature.setAttribute(field_ids.get("proc_sidepath"), is_sidepath)
    
    return is_sidepath


def update_feature_highway_class(feature, sidepath_dict, field_ids, highway_class_list):
    id = feature.attribute('id')
    is_sidepath_of = feature.attribute('is_sidepath:of')

    if not is_sidepath_of and len(sidepath_dict[id]['highway']):
        max_value = max(sidepath_dict[id]['highway'].values())
        max_keys = [key for key, value in sidepath_dict[id]['highway'].items() if value == max_value]
        min_index = len(highway_class_list) - 1
        for key in max_keys:
            if key in highway_class_list and highway_class_list.index(key) < min_index:
                min_index = highway_class_list.index(key)
        is_sidepath_of = highway_class_list[min_index]

    feature.setAttribute(field_ids.get("proc_highway"), is_sidepath_of)
    return is_sidepath_of


def transfer_maxspeed(feature, sidepath_dict, field_ids):
    is_sidepath_of = feature.attribute('proc_highway')
    id = feature.attribute('id')
    if is_sidepath_of in sidepath_dict[id]['maxspeed']:
        maxspeed = sidepath_dict[id]['maxspeed'][is_sidepath_of]
        if maxspeed:
            feature.setAttribute(field_ids.get("proc_maxspeed"), d.getNumber(maxspeed))


def transfer_sidepath_names(feature, sidepath_dict, field_ids):
    id = feature.attribute('id')
    if len(sidepath_dict[id]['name']):
        name = max(sidepath_dict[id]['name'], key=lambda k: sidepath_dict[id]['name'][k])  # Most frequent name
        if name:
            feature.setAttribute(field_ids.get("name"), name)


def update_sidepath_attributes(layer, sidepath_dict, field_ids, highway_class_list):
    with edit(layer):
        for feature in layer.getFeatures():
            hw = feature.attribute('highway')
            maxspeed = determine_maxspeed(feature, hw)
            if hw not in ['cycleway', 'footway', 'path', 'bridleway', 'steps', 'bridleway, track']:
                feature.setAttribute(field_ids.get("proc_highway"), hw)
                feature.setAttribute(field_ids.get("proc_maxspeed"), d.getNumber(maxspeed))
                # layer.changeAttributeValue(feature.id(), field_ids.get("proc_highway"), hw)
                # layer.changeAttributeValue(feature.id(), field_ids.get("proc_maxspeed"), maxspeed)
                layer.updateFeature(feature)
                continue
            
            id = feature.attribute('id')
            if id not in sidepath_dict:
                continue

            is_sidepath = update_feature_sidepath_status(feature, sidepath_dict, field_ids, highway_class_list)
            layer.updateFeature(feature)
            if is_sidepath == 'yes':
                is_sidepath_of = update_feature_highway_class(feature, sidepath_dict, field_ids, highway_class_list)
                layer.updateFeature(feature)
                transfer_maxspeed(feature, sidepath_dict, field_ids)
                transfer_sidepath_names(feature, sidepath_dict, field_ids)
                layer.updateFeature(feature)


def calculate_offset_cycleway(offset_distance, width):
    #TODO: more precise offset calculation taking "parking:", "placement", "width:lanes" and other Tags into account
    if offset_distance == 'realistic':
        return width / 2
    else:
        return d.getNumber(offset_distance)


def calculate_offset_sidewalk(offset_distance, width):
    if offset_distance == 'realistic':
        return width / 2 + 2
    else:
        return d.getNumber(offset_distance)
    

def update_offset_attributes(layer, field_ids, p):
    cycleway_conditions = ['lane', 'track', 'share_busway']
    sidewalk_conditions = ['yes', 'designated', 'permissive']
    with edit(layer):
        for feature in layer.getFeatures():
            highway = feature.attribute('highway')
            offset_cycleway_left = offset_cycleway_right = offset_sidewalk_left = offset_sidewalk_right = 0
            width = 0

            if p.offset_distance == 'realistic':
                width = d.getNumber(feature.attribute('width')) or p.default_highway_width_dict.get(highway, p.default_highway_width_fallback)

            cycleway_features_left = [feature.attribute('cycleway'), feature.attribute('cycleway:both'), feature.attribute('cycleway:left')]
            cycleway_features_right = [feature.attribute('cycleway'), feature.attribute('cycleway:both'), feature.attribute('cycleway:right')]

            sidewalk_features_left = [feature.attribute('sidewalk:bicycle'), feature.attribute('sidewalk:both:bicycle'), feature.attribute('sidewalk:left:bicycle')]
            sidewalk_features_right = [feature.attribute('sidewalk:bicycle'), feature.attribute('sidewalk:both:bicycle'), feature.attribute('sidewalk:right:bicycle')]

            if any(cw in cycleway_conditions for cw in cycleway_features_left):
                offset_cycleway_left = calculate_offset_cycleway(p.offset_distance, width)
                layer.changeAttributeValue(feature.id(), field_ids.get('offset_cycleway_left'), offset_cycleway_left)

            if any(cw in cycleway_conditions for cw in cycleway_features_right):
                offset_cycleway_right = calculate_offset_cycleway(p.offset_distance, width)
                layer.changeAttributeValue(feature.id(), field_ids.get('offset_cycleway_right'), offset_cycleway_right)

            if any(sw in sidewalk_conditions for sw in sidewalk_features_left):
                offset_sidewalk_left = calculate_offset_sidewalk(p.offset_distance, width)
                layer.changeAttributeValue(feature.id(), field_ids.get('offset_sidewalk_left'), offset_sidewalk_left)

            if any(sw in sidewalk_conditions for sw in sidewalk_features_right):
                offset_sidewalk_right = calculate_offset_sidewalk(p.offset_distance, width)
                layer.changeAttributeValue(feature.id(), field_ids.get('offset_sidewalk_right'), offset_sidewalk_right)



def process_offset_lines(layer, expression, distance_expression, output_key, qgis_layers):
    processing.run('qgis:selectbyexpression', {'INPUT': layer, 'EXPRESSION': expression})
    offset_layer = processing.run('native:offsetline', {
        'INPUT': QgsProcessingFeatureSourceDefinition(layer.id(), selectedFeaturesOnly=True),
        'DISTANCE': QgsProperty.fromExpression(distance_expression),
        'OUTPUT': 'memory:'
    })['OUTPUT']
    qgis_layers[output_key] = offset_layer


def update_offset_layer_attributes(layer, field_ids, qgis_layers, d):
    def set_common_attributes(feature, offset_layer, type, side):
        offset_layer.changeAttributeValue(feature.id(), field_ids.get('offset'), feature.attribute(f'offset_{type}_{side}'))
        offset_layer.changeAttributeValue(feature.id(), field_ids.get('type'), type)
        offset_layer.changeAttributeValue(feature.id(), field_ids.get('side'), side)
        offset_layer.changeAttributeValue(feature.id(), field_ids.get("proc_sidepath"), 'yes')
        offset_layer.changeAttributeValue(feature.id(), field_ids.get("proc_highway"), feature.attribute('highway'))
        offset_layer.changeAttributeValue(feature.id(), field_ids.get("proc_maxspeed"), d.getNumber(feature.attribute('maxspeed')))

        attributes = ['width', 'oneway', 'oneway:bicycle', 'traffic_sign']
        for attr in attributes:
            offset_layer.changeAttributeValue(feature.id(), offset_layer.fields().indexOf(attr), d.deriveAttribute(feature, attr, type, side, 'str' if 'oneway' in attr else 'float'))

    def set_implicit_surface_smoothness(feature, offset_layer, type, side):
        if type != 'cycleway' or (feature.attribute(f'cycleway:{side}') == 'track' 
                                or feature.attribute('cycleway:both') == 'track'
                                or feature.attribute('cycleway') == 'track'
                                or any(feature.attribute(f'{type}:{side}:{attr}') is not None for attr in ['surface', 'smoothness'])):
                offset_layer.changeAttributeValue(feature.id(), offset_layer.fields().indexOf(
                    'surface'), d.deriveAttribute(feature, 'surface', 'cycleway', side, 'str'))
                offset_layer.changeAttributeValue(feature.id(), offset_layer.fields().indexOf(
                    'smoothness'), d.deriveAttribute(feature, 'smoothness', 'cycleway', side, 'str'))

    def set_cycleway_attributes(feature, offset_layer, side):
        cycleway_attributes = ['separation', 'separation:both', 'separation:left', 'separation:right',
                       'buffer', 'buffer:both', 'buffer:left' , 'buffer:right',
                       'traffic_mode:both', 'traffic_mode:left', 'traffic_mode:right', 'surface:colour']

        for attr in cycleway_attributes:
            offset_layer.changeAttributeValue(feature.id(), offset_layer.fields().indexOf(attr), d.deriveAttribute(feature, attr, 'cycleway', side, 'str'))


    for side in ['left', 'right']:
        for type in ['cycleway', 'sidewalk']:
            layer_name = f'offset_{type}_{side}_layer'
            offset_layer = qgis_layers.get(layer_name, None)
            if offset_layer is None:
                continue

            with edit(offset_layer):
                for feature in offset_layer.getFeatures():
                    set_common_attributes(feature, offset_layer, type, side)
                    set_implicit_surface_smoothness(feature, offset_layer, type, side)
                    if type == 'cycleway':
                        set_cycleway_attributes(feature, offset_layer, side)


def merge_layers(layer, qgis_layers):
    layers_to_merge = [layer] + list(qgis_layers.values())
    return processing.run('native:mergevectorlayers', {'LAYERS': layers_to_merge, 'OUTPUT': 'memory:'})['OUTPUT']


def delete_if_no_access(layer, feature):
    if d.getAccess(feature, 'bicycle') and d.getAccess(feature, 'bicycle') not in ALLOWED_BICYCLE_ACCESS:
        layer.deleteFeature(feature.id())


def delete_informal_paths(layer, feature):
    if feature.attribute('highway') == 'path' and feature.attribute('informal') == 'yes' and feature.attribute('bicycle') is None:
        layer.deleteFeature(feature.id())


def determine_way_type(layer, feature):
    way_type = ''
    highway = feature.attribute('highway')
    segregated = feature.attribute('segregated')
    bicycle = feature.attribute('bicycle')
    foot = feature.attribute('foot')
    vehicle = feature.attribute('vehicle')
    is_sidepath = feature.attribute('is_sidepath')
    side = feature.attribute('side')

    if feature.attribute('bicycle_road') == 'yes' and not side:
        return 'bicycle road'
    
    if any(feature.attribute(attr) == 'link' for attr in LINK_ATTRIBUTES):
        return 'link'
    
    if any(feature.attribute(attr) == 'crossing' for attr in CROSSING_ATTRIBUTES):
        return 'crossing'

    if highway in SHARED_FOOTWAY_HIGHWAYS:
        if bicycle in ['yes', 'designated', 'permissive']:
            return 'shared footway'
        else:
            layer.deleteFeature(feature.id()) # Todo this should be somewhere else
    
    if highway == 'path':
        if foot == 'designated' and bicycle != 'designated':
            return 'shared footway'
        return 'segregated path' if segregated == 'yes' else 'shared path'
    
    if highway == 'cycleway':
        if foot in ['yes', 'designated', 'permissive']:
            return 'shared path'
        if d.deriveSeparation(feature, 'foot') == 'no':
            return 'segregated path'
        if not is_sidepath in ['yes', 'no']:
            return 'cycle track' if feature.attribute('proc_sidepath') == 'yes' else 'cycle path'
        if is_sidepath == 'yes':
            if d.deriveSeparation(feature, 'motor_vehicle') not in [None, 'no', 'none']:
                return 'cycle track' if 'kerb' in d.deriveSeparation(feature, 'motor_vehicle') or 'tree_row' in d.deriveSeparation(feature, 'motor_vehicle') else 'cycle lane (protected)'
            return 'cycle track'
        return 'cycle path'
    
    if highway in ['service', 'track']:
        return 'track or service'
    
    if not side:
        lane_markings = feature.attribute('lane_markings')
        if lane_markings == 'yes' or (lane_markings != 'yes' and highway in ['motorway', 'trunk', 'primary', 'secondary']):
            return 'shared traffic lane'
        return 'shared road'
    
    type = feature.attribute('type')
    if type == 'sidewalk':
        return 'shared footway'
    
    if any(feature.attribute(attr) == 'lane' for attr in ['cycleway', 'cycleway:both', 'cycleway:left', 'cycleway:right']):
        if feature.attribute('cycleway:lanes') and 'no|lane|no' in feature.attribute('cycleway:lanes'):
            return 'cycle lane (central)'
        if d.deriveSeparation(feature, 'motor_vehicle') not in [None, 'no', 'none']:
            return 'cycle lane (protected)'
        if any(feature.attribute(attr) == 'exclusive' for attr in ['cycleway:lane', 'cycleway:both:lane', 'cycleway:left:lane', 'cycleway:right:lane']):
            return 'cycle lane (exclusive)'
        return 'cycle lane (advisory)'
    
    if any(feature.attribute(attr) == 'track' for attr in ['cycleway', 'cycleway:both', 'cycleway:left', 'cycleway:right']):
        if any(feature.attribute(attr) in ['yes', 'designated', 'permissive'] for attr in ['cycleway:foot', 'cycleway:both:foot', 'cycleway:left:foot', 'cycleway:right:foot']):
            return 'shared path'
        if any(feature.attribute(attr) == 'yes' for attr in ['cycleway:segregated', 'cycleway:both:segregated', 'cycleway:left:segregated', 'cycleway:right:segregated']):
            return 'segregated path'
        if any(feature.attribute(attr) == 'no' for attr in ['cycleway:segregated', 'cycleway:both:segregated', 'cycleway:left:segregated', 'cycleway:right:segregated']):
            return 'shared path'
        if d.deriveSeparation(feature, 'foot') == 'no':
            return 'segregated path'
        if d.deriveSeparation(feature, 'motor_vehicle') not in [None, 'no', 'none']:
            return 'cycle track' if 'kerb' in d.deriveSeparation(feature, 'motor_vehicle') or 'tree_row' in d.deriveSeparation(feature, 'motor_vehicle') else 'cycle lane (protected)'
        return 'cycle track'
    
    if any(feature.attribute(attr) == 'share_busway' for attr in ['cycleway', 'cycleway:both', 'cycleway:left', 'cycleway:right']):
        return 'shared bus lane'
    
    if any(feature.attribute(attr) == 'yes' for attr in ['sidewalk:bicycle', 'sidewalk:both:bicycle', 'sidewalk:left:bicycle', 'sidewalk:right:bicycle']):
        return 'shared footway'
    
    lane_markings = feature.attribute('lane_markings')
    if lane_markings == 'yes' or (lane_markings != 'yes' and highway in ['primary', 'secondary']):
        return 'shared traffic lane'
    return 'shared road'


def update_way_type(layer, field_ids):
    with edit(layer):
        for feature in layer.getFeatures():
            delete_if_no_access(layer, feature)
            delete_informal_paths(layer, feature)
            
            way_type = determine_way_type(layer, feature)
            
            if way_type:
                layer.changeAttributeValue(feature.id(), field_ids.get('way_type'), way_type)


def determine_cycleway_oneway(oneway, cycleway_oneway, oneway_bicycle, way_type, side, p):
    oneway_value_list = ['yes', 'no', '-1', 'alternating', 'reversible']

    if oneway in oneway_value_list:
        return oneway
    if cycleway_oneway in oneway_value_list:
        return cycleway_oneway
    if way_type in ['cycle track', 'shared path', 'shared footway'] and side:
        return p.default_oneway_cycle_track
    if 'cycle lane' in way_type:
        return p.default_oneway_cycle_lane
    if oneway_bicycle in oneway_value_list:
        return oneway_bicycle

    return 'no'


def determine_shared_road_oneway(oneway, oneway_bicycle):
    oneway_value_list = ['yes', 'no', '-1', 'alternating', 'reversible']

    if not oneway_bicycle or oneway == oneway_bicycle:
        return oneway if oneway in oneway_value_list else 'no'
    if oneway_bicycle == 'no':
        return oneway + '_motor_vehicles' if oneway in oneway_value_list else 'no'

    return 'yes'


def derive_oneway_status(feature):
    proc_oneway = NULL
    side = feature.attribute('side')
    oneway = feature.attribute('oneway')
    oneway_bicycle = feature.attribute('oneway:bicycle')
    cycleway_oneway = feature.attribute('cycleway:oneway')
    way_type = feature.attribute('way_type')

    if way_type in ['cycle path', 'cycle track', 'shared path', 'segregated path', 'shared footway', 'crossing', 'link', 'cycle lane (advisory)', 'cycle lane (exclusive)', 'cycle lane (protected)', 'cycle lane (central)']:
        proc_oneway = determine_cycleway_oneway(oneway, cycleway_oneway, oneway_bicycle, way_type, side, p)

    elif way_type == 'shared bus lane':
        proc_oneway = 'yes'

    elif way_type in ['shared road', 'shared traffic lane', 'bicycle road', 'track or service']:
        proc_oneway = determine_shared_road_oneway(oneway, oneway_bicycle)

    proc_oneway = proc_oneway or 'unknown'
    return proc_oneway


def derive_mandatory_use(feature, way_type, proc_oneway):
    proc_mandatory = None
    traffic_sign = feature.attribute('traffic_sign')

    if way_type in ['bicycle road', 'shared road', 'shared traffic lane', 'track or service']:
        if feature.attribute('cycleway') in ['lane', 'share_busway'] or feature.attribute('cycleway:both') in ['lane', 'share_busway'] or ('yes' in proc_oneway and feature.attribute('cycleway:right') in ['lane', 'share_busway']):
            proc_mandatory = 'use_sidepath'
        elif feature.attribute('cycleway') == 'track' or feature.attribute('cycleway:both') == 'track' or ('yes' in proc_oneway and feature.attribute('cycleway:right') == 'track'):
            proc_mandatory = 'optional_sidepath'
        if feature.attribute('bicycle') in ['use_sidepath', 'optional_sidepath']:
            proc_mandatory = feature.attribute('bicycle')
    elif feature.attribute('proc_sidepath') == 'yes':
        if traffic_sign:
            for sign in d.getDelimitedValues(traffic_sign.replace(',', ';'), ';', 'string'):
                if any(mandatory_sign in sign for mandatory_sign in p.not_mandatory_traffic_sign_list):
                    proc_mandatory = 'no'
                elif any(mandatory_sign in sign for mandatory_sign in p.mandatory_traffic_sign_list):
                    proc_mandatory = 'yes'

    if feature.attribute('highway') in p.cycling_highway_prohibition_list or feature.attribute('bicycle') == 'no':
        proc_mandatory = 'prohibited'

    return proc_mandatory, traffic_sign


def derive_extra_filters(way_type, proc_mandatory):
    filter_usable = 0 if proc_mandatory in ['prohibited', 'use_sidepath'] else 1
    filter_way_type = None

    if way_type in ['cycle path', 'cycle track', 'shared path', 'segregated path', 'shared footway', 'cycle lane (protected)']:
        filter_way_type = 'separated'
    elif way_type in ['cycle lane (advisory)', 'cycle lane (exclusive)', 'cycle lane (central)', 'link', 'crossing']:
        filter_way_type = 'cycle lanes'
    elif way_type == 'bicycle road':
        filter_way_type = 'bicycle road'
    elif way_type in ['shared road', 'shared traffic lane', 'shared bus lane', 'track or service']:
        filter_way_type = 'shared traffic'

    return filter_usable, filter_way_type


def get_precalculated_feature_width(feature):
    #width for cycle lanes and sidewalks have already been derived from original tags when calculating way offsets
    width = d.getNumber(feature.attribute('cycleway:width'))
    if width:
        return width

    width = d.getNumber(feature.attribute('width'))
    if width:
        return width


def get_default_width_for_way_type(feature):
    way_type = feature.attribute('way_type')

    if way_type in ['cycle path', 'shared path', 'cycle lane (protected)']:
        width = p.default_highway_width_dict.get('path', None)
    elif way_type == 'shared footway':
        width = p.default_highway_width_dict.get('footway', None)
    else:
        width = p.default_highway_width_dict.get('cycleway', None)
    return width


# Split parking:both-keys into left and right values
def split_both_values_to_left_right(both_value, left_value, right_value):
    if both_value:
        left_value = left_value or both_value
        right_value = right_value or both_value
    return left_value, right_value


def calculate_parking_width(parking_side, parking_width, parking_orientation, p):
    if parking_side in ['lane', 'half_on_kerb'] and not parking_width:
        if parking_orientation == 'diagonal':
            parking_width = p.default_width_parking_diagonal
        elif parking_orientation == 'perpendicular':
            parking_width = p.default_width_parking_perpendicular
        else:
            parking_width = p.default_width_parking_parallel
    if parking_side == 'half_on_kerb':
        parking_width = float(parking_width) / 2
    return parking_width or 0


def get_width_footway(feature):
    width = d.getNumber(feature.attribute('width'))
    footway_width = d.getNumber(feature.attribute('footway:width'))

    if not width:
        return NULL

    if footway_width:
        return width - footway_width

    return width / 2


def calc_feature_width(feature, proc_oneway):
    data_missing = []
    way_type = feature.attribute('way_type')
    proc_width = None
    if way_type in ['cycle path', 'cycle track', 'shared path',
                    'shared footway', 'crossing', 'link',
                    'cycle lane (advisory)', 'cycle lane (exclusive)', 'cycle lane (protected)',
                    'cycle lane (central)']:
            width = get_precalculated_feature_width(feature)
            if not width:
                width = get_default_width_for_way_type(feature)
                if proc_oneway == 'no':
                    width *= 1.6
                data_missing.append("width")
                return width, data_missing
            return width, data_missing

    if way_type == 'segregated path':
        highway = feature.attribute('highway')

        if highway == 'path':
            proc_width = d.getNumber(feature.attribute('cycleway:width'))
            if proc_width:
                return proc_width, data_missing
            proc_width = get_width_footway(feature)
            data_missing.append('width')
        else:
            proc_width = d.getNumber(feature.attribute('width'))

        if not proc_width:
            proc_width = p.default_highway_width_dict.get('path', None)
            if proc_oneway == 'no':
                proc_width *= 1.6
            data_missing.append('width')

        return proc_width, data_missing

    if way_type in ['shared road', 'shared traffic lane', 'shared bus lane', 'bicycle road', 'track or service']:
        #on shared traffic or bus lanes, use a width value based on lane width, not on carriageway width
        if way_type in ['shared traffic lane', 'shared bus lane']:
            width_lanes = feature.attribute('width:lanes')
            width_lanes_forward = feature.attribute('width:lanes:forward')
            width_lanes_backward = feature.attribute('width:lanes:backward')
            side = feature.attribute('side')

            if ('yes' in proc_oneway or way_type != 'shared bus lane') and width_lanes and '|' in width_lanes:
                #TODO: at the moment, forward/backward can only be processed for shared bus lanes, since there are no separate geometries for shared road lanes
                #TODO: for bus lanes, currently only assuming that the right lane is the bus lane. Instead derive lane position from "psv:lanes" or "bus:lanes", if specified
                proc_width = d.getNumber(width_lanes[width_lanes.rfind('|') + 1:])
            elif (way_type == 'shared bus lane' and not 'yes' in proc_oneway) and side == 'right' and width_lanes_forward and '|' in width_lanes_forward:
                proc_width = d.getNumber(width_lanes_forward[width_lanes_forward.rfind('|') + 1:])
            elif (way_type == 'shared bus lane' and not 'yes' in proc_oneway) and side == 'left' and width_lanes_backward and '|' in width_lanes_backward:
                proc_width = d.getNumber(width_lanes_backward[width_lanes_backward.rfind('|') + 1:])
            else:
                if way_type == 'shared bus lane':
                    proc_width = p.default_width_bus_lane
                else:
                    proc_width = p.default_width_traffic_lane
                    data_missing.append('width:lanes')

        if proc_width:
            return proc_width, data_missing

        #effective width (usable width of a road for flowing traffic) can be mapped explicitely
        proc_width = d.getNumber(feature.attribute('width:effective'))
        if proc_width:
            return proc_width, data_missing

        #try to use lane count and a default lane width if no width and no width:effective is mapped
        #(usually, this means, there are lane markings (see above), but sometimes "lane" tag is misused or "lane_markings" isn't mapped)
        width = d.getNumber(feature.attribute('width'))
        if not width:
            lanes = d.getNumber(feature.attribute('lanes'))
            if lanes:
                proc_width = lanes * p.default_width_traffic_lane
                #TODO: take width:lanes into account, if mapped

        if proc_width:
            return proc_width, data_missing

        parking_left, parking_right = get_parking_status(feature)
        parking_left_width, parking_right_width = get_parking_width(feature)
        cycleway_attrs, buffer_attrs = make_cycleway_buffers(feature)

        width = d.getNumber(feature.attribute('width'))
        if not width:
            width = assure_default_width(feature, proc_oneway)
            data_missing.append('width')

        cycleway_right_buffer_left = False
        cycleway_right_buffer_right = False
        cycleway_left_buffer_left = False
        cycleway_left_buffer_right = False

        if cycleway_attrs['cycleway_right'] == "lane": # TODO is this even needed?
            cycleway_right_buffer_left, cycleway_right_buffer_right = process_buffer(buffer_attrs, 'right')

        if cycleway_attrs['cycleway_left'] == "lane": # TODO is this even needed?
            cycleway_left_buffer_left, cycleway_left_buffer_right = process_buffer(buffer_attrs, 'left')

        for buffer in [cycleway_right_buffer_left, cycleway_right_buffer_right, cycleway_left_buffer_left, cycleway_left_buffer_right]:
            if not buffer or buffer == 'no' or buffer == 'none':
                buffer = 0

        buffer = d.getNumber(cycleway_right_buffer_left) + d.getNumber(cycleway_right_buffer_right) + d.getNumber(cycleway_left_buffer_left) + d.getNumber(cycleway_left_buffer_right)
        proc_width = width - d.getNumber(cycleway_attrs['cycleway_right_width']) - d.getNumber(cycleway_attrs['cycleway_left_width']) - buffer

        if parking_right or parking_left:
            proc_width = proc_width - d.getNumber(parking_right_width) - d.getNumber(parking_left_width)
        elif way_type == 'shared road':
            if 'yes' not in proc_oneway:
                proc_width = min(proc_width, 5.5)
            else:
                proc_width = min(proc_width, 4)

        if proc_width < p.default_width_traffic_lane and 'width' in data_missing:
            proc_width = p.default_width_traffic_lane

        if not proc_width:
            proc_width = NULL

        return proc_width, data_missing
    return proc_width, data_missing


def get_parking_status(feature):
    parking_left = feature.attribute('parking:left')
    parking_right = feature.attribute('parking:right')
    parking_both = feature.attribute('parking:both')

    parking_left, parking_right = split_both_values_to_left_right(parking_both, parking_left, parking_right)

    return parking_left, parking_right


def get_parking_width(feature): 
    #derive effective road width from road width, parking and cycle lane informations
    #subtract parking and cycle lane width from carriageway width to get effective width (usable width for driving)
    #derive parking lane width
    parking_left = feature.attribute('parking:left')
    parking_left_orientation = feature.attribute('parking:left:orientation')
    parking_left_width = d.getNumber(feature.attribute('parking:left:width'))

    parking_right = feature.attribute('parking:right')
    parking_right_orientation = feature.attribute('parking:right:orientation')
    parking_right_width = d.getNumber(feature.attribute('parking:right:width'))

    parking_both = feature.attribute('parking:both')
    parking_both_orientation = feature.attribute('parking:both:orientation')
    parking_both_width = d.getNumber(feature.attribute('parking:both:width'))

    parking_left, parking_right = split_both_values_to_left_right(parking_both, parking_left, parking_right)
    parking_left_orientation, parking_right_orientation = split_both_values_to_left_right(parking_both_orientation, parking_left_orientation, parking_right_orientation)
    parking_left_width, parking_right_width = split_both_values_to_left_right(parking_both_width, parking_left_width, parking_right_width)

    parking_right_width = calculate_parking_width(parking_right, parking_right_width, parking_right_orientation, p)
    parking_left_width = calculate_parking_width(parking_left, parking_left_width, parking_left_orientation, p)

    return parking_left_width, parking_right_width


def get_cycleway_attributes(feature):
    return {
        'cycleway': feature.attribute('cycleway'),
        'cycleway_left': feature.attribute('cycleway:left'),
        'cycleway_right': feature.attribute('cycleway:right'),
        'cycleway_both': feature.attribute('cycleway:both'),
        'cycleway_width': feature.attribute('cycleway:width'),
        'cycleway_left_width': feature.attribute('cycleway:left:width'),
        'cycleway_right_width': feature.attribute('cycleway:right:width'),
        'cycleway_both_width': feature.attribute('cycleway:both:width')
    }


def get_buffer_attributes(feature):
    buffer_feature_attributes = {}
    buffer_types = ['', 'left', 'right', 'both']
    sides = ['', 'left', 'right', 'both']
    for buffer_type in buffer_types:
        for side in sides:
            key = f"cycleway{'_' + side if side else ''}:buffer{'_' + buffer_type if buffer_type else ''}"
            key = key.replace(':', '_')
            feature_key = key.replace('_', ':')
            buffer_feature_attributes[key] = feature.attribute(feature_key)
    return buffer_feature_attributes


def process_cycleway_sides(feature_attributes, oneway):
    if feature_attributes['cycleway']:
        if not feature_attributes['cycleway_right']:
            feature_attributes['cycleway_right'] = feature_attributes['cycleway']
        if not feature_attributes['cycleway_left'] and (not oneway or oneway == 'no'):
            feature_attributes['cycleway_left'] = feature_attributes['cycleway']
    if feature_attributes['cycleway_both']:
        if not feature_attributes['cycleway_right']:
            feature_attributes['cycleway_right'] = feature_attributes['cycleway_both']
        if not feature_attributes['cycleway_left']:
            feature_attributes['cycleway_left'] = feature_attributes['cycleway_both']
    return feature_attributes


def process_cycleway_widths(feature_attributes, oneway):
    if feature_attributes['cycleway_right'] == 'lane' or feature_attributes['cycleway_left'] == 'lane':
        if feature_attributes['cycleway_width']:
            if not feature_attributes['cycleway_right_width']:
                feature_attributes['cycleway_right_width'] = feature_attributes['cycleway_width']
            if not feature_attributes['cycleway_left_width'] and (not oneway or oneway == 'no'):
                feature_attributes['cycleway_left_width'] = feature_attributes['cycleway_width']
        if feature_attributes['cycleway_both_width']:
            if not feature_attributes['cycleway_right_width']:
                feature_attributes['cycleway_right_width'] = feature_attributes['cycleway_both_width']
            if not feature_attributes['cycleway_left_width']:
                feature_attributes['cycleway_left_width'] = feature_attributes['cycleway_both_width']
    return feature_attributes


def process_buffer(buffer_feature_attributes, side):
    buffer_left = NULL
    buffer_right = NULL
    buffer_tags_left = [f'cycleway_{side}_buffer_left', f'cycleway_{side}_buffer_both', f'cycleway_{side}_buffer',
                        'cycleway_both_buffer_left', 'cycleway_both_buffer_both', 'cycleway_both_buffer',
                        'cycleway_buffer_left', 'cycleway_buffer_both', 'cycleway_buffer']
    buffer_tags_right = [f'cycleway_{side}_buffer_right', f'cycleway_{side}_buffer_both', f'cycleway_{side}_buffer',
                         'cycleway_both_buffer_right', 'cycleway_both_buffer_both', 'cycleway_both_buffer',
                         'cycleway_buffer_right', 'cycleway_buffer_both', 'cycleway_buffer']

    for tag in buffer_tags_left:
        if not buffer_left:
            buffer_left = buffer_feature_attributes[tag]
        else:
            break
    for tag in buffer_tags_right:
        if not buffer_right:
            buffer_right = buffer_feature_attributes[tag]
        else:
            break

    return buffer_left, buffer_right


def make_cycleway_buffers(feature):
    cycleway_attrs = get_cycleway_attributes(feature)
    buffer_attrs = get_buffer_attributes(feature)

    oneway = False #FIXME where does this value come from?

    cycleway_attrs = process_cycleway_sides(cycleway_attrs, oneway)
    cycleway_attrs = process_cycleway_widths(cycleway_attrs, oneway)

    if cycleway_attrs['cycleway_right'] == 'lane':
        if not cycleway_attrs['cycleway_right_width']:
            cycleway_attrs['cycleway_right_width'] = p.default_width_cycle_lane

    if cycleway_attrs['cycleway_left'] == 'lane':
        if not cycleway_attrs['cycleway_left_width']:
            cycleway_attrs['cycleway_left_width'] = p.default_width_cycle_lane

    cycleway_attrs['cycleway_right_width'] = cycleway_attrs['cycleway_right_width'] or 0
    cycleway_attrs['cycleway_left_width'] = cycleway_attrs['cycleway_left_width'] or 0


    return cycleway_attrs, buffer_attrs


def assure_default_width(feature, proc_oneway):
    highway = feature.attribute('highway')
    width = d.getNumber(feature.attribute('width'))
    if not width:
        width = p.default_highway_width_dict.get(highway, p.default_highway_width_fallback)
        if 'yes' in proc_oneway:
            width = round(width / 1.6, 1)
    return width


def get_default_surface(feature, way_type):
    if way_type in ['cycle lane (advisory)', 'cycle lane (exclusive)', 'cycle lane (protected)', 'cycle lane (central)']:
        return p.default_cycleway_surface_lanes
    elif way_type == 'cycle track':
        return p.default_cycleway_surface_tracks
    elif way_type == 'track or service':
        tracktype = feature.attribute('tracktype')
        return p.default_track_surface_dict.get(tracktype, p.default_track_surface_dict['grade3'])
    else:
        highway = feature.attribute('highway')
        return p.default_highway_surface_dict.get(highway, p.default_highway_surface_dict['path'])


def derive_surface(feature):
    proc_surface = None
    data_missing = []
    way_type = feature.attribute('way_type')

    surface_bicycle = feature.attribute('surface:bicycle')
    if surface_bicycle:
        if surface_bicycle in p.surface_factor_dict:
            proc_surface = surface_bicycle
        elif ';' in surface_bicycle:
            proc_surface = d.getWeakestSurfaceValue(d.getDelimitedValues(surface_bicycle, ';', 'string'))

    if proc_surface:
        return proc_surface, data_missing

    if way_type == 'segregated path':
        proc_surface = feature.attribute('cycleway:surface')
        if not proc_surface:
            surface = feature.attribute('surface')
            if surface:
                proc_surface = surface
            else:
                highway = feature.attribute('highway')
                proc_surface = p.default_highway_surface_dict.get(highway, p.default_highway_surface_dict.get('path'))
            data_missing.append('surface')
    else:
        proc_surface = feature.attribute('surface')
        if not proc_surface:
            proc_surface = get_default_surface(feature, way_type)
            data_missing.append('surface')

    #if more than one surface value is tagged (delimited by a semicolon), use the weakest one
    if ';' in proc_surface:
        proc_surface = d.getWeakestSurfaceValue(d.getDelimitedValues(proc_surface, ';', 'string'))
    if proc_surface not in p.surface_factor_dict:
        proc_surface = NULL

    return proc_surface, data_missing


def derive_smoothness(feature):
    # proc_smoothness = feature.attribute('smoothness')
    #in rare cases, surface or smoothness is explicitely tagged for bicycles - check that first
    data_missing = []
    smoothness_bicycle = feature.attribute('smoothness:bicycle')
    proc_smoothness = p.smoothness_factor_dict.get(smoothness_bicycle, NULL)
    way_type = feature.attribute('way_type')
    
    if not proc_smoothness:
        if way_type == 'segregated path':
            proc_smoothness = feature.attribute('cycleway:smoothness') or feature.attribute('smoothness')
        else:
            proc_smoothness = feature.attribute('smoothness')
        
        if not proc_smoothness:
            data_missing.append('smoothness')

    if proc_smoothness not in p.smoothness_factor_dict:
        proc_smoothness = NULL

    return proc_smoothness, data_missing


def is_parking_allowed(parking_side):
    return parking_side and parking_side != 'no'


def determine_traffic_mode_left(way_type, is_sidepath, side, parking_right, parking_left, traffic_mode_right):
    if way_type == 'cycle path':
        return 'no'
    elif way_type in ['cycle track', 'shared path', 'segregated path', 'shared footway'] and is_sidepath == 'yes':
        if ((side == 'right' and is_parking_allowed(parking_right)) or 
            (side == 'left' and is_parking_allowed(parking_left))) and traffic_mode_right != 'parking':
            return 'parking'
        else:
            return 'motor_vehicle'
    elif 'cycle lane' in way_type or way_type in ['shared road', 'shared traffic lane', 'shared bus lane', 'crossing']:
        return 'motor_vehicle'
    return None


def determine_traffic_mode_right(way_type, is_sidepath, side, parking_right, parking_left, traffic_mode_left):
    if way_type == 'cycle path':
        return 'no'
    elif way_type == 'crossing':
        return 'motor_vehicle'
    elif 'cycle lane' in way_type:
        if ((side == 'right' and is_parking_allowed(parking_right)) or 
            (side == 'left' and is_parking_allowed(parking_left))) and traffic_mode_left != 'parking':
            return 'parking'
        else:
            return 'foot'
    elif way_type in ['cycle track', 'shared path', 'segregated path', 'shared footway'] and is_sidepath == 'yes':
        return 'foot'
    return None


def determine_separation(feature, right_hand_traffic, traffic_mode_left, traffic_mode_right):
    separation = feature.attribute('separation')
    separation_left = feature.attribute('separation:left')
    separation_right = feature.attribute('separation:right')
    separation_both = feature.attribute('separation:both')

    separation_left, separation_right = split_both_values_to_left_right(separation_both, separation_left, separation_right)

    if separation:
        if right_hand_traffic:
            if traffic_mode_left in ['motor_vehicle', 'psv', 'parking']:
                separation_left = separation_left or separation
            elif traffic_mode_right == 'motor_vehicle':
                separation_right = separation_right or separation
        else:
            if traffic_mode_right in ['motor_vehicle', 'psv', 'parking']:
                separation_right = separation_right or separation
            elif traffic_mode_left == 'motor_vehicle':
                separation_left = separation_left or separation

    separation_left = separation_left or 'no'
    separation_right = separation_right or 'no'

    return separation_left, separation_right


def determine_buffer(feature, right_hand_traffic, traffic_mode_left, traffic_mode_right):
    buffer = d.getNumber(feature.attribute('buffer'))
    buffer_left = d.getNumber(feature.attribute('buffer:left'))
    buffer_right = d.getNumber(feature.attribute('buffer:right'))
    buffer_both = d.getNumber(feature.attribute('buffer:both'))

    buffer_left, buffer_right = split_both_values_to_left_right(buffer_both, buffer_left, buffer_right)

    if buffer:
        if right_hand_traffic:
            if traffic_mode_left in ['motor_vehicle', 'psv', 'parking']:
                buffer_left = buffer_left or buffer
            elif traffic_mode_right == 'motor_vehicle':
                buffer_right = buffer_right or buffer
        else:
            if traffic_mode_right in ['motor_vehicle', 'psv', 'parking']:
                buffer_right = buffer_right or buffer
            elif traffic_mode_left == 'motor_vehicle':
                buffer_left = buffer_left or buffer

    return buffer_left, buffer_right


def derive_traffic_modes(feature, right_hand_traffic):
    data_missing = []
    traffic_mode_left = NULL
    way_type = feature.attribute('way_type')

    if way_type == 'cycle lane (central)':
        traffic_mode_left = 'motor_vehicle'
        traffic_mode_right = 'motor_vehicle'
        return traffic_mode_left, traffic_mode_right, data_missing

    traffic_mode_left = feature.attribute('traffic_mode:left')
    traffic_mode_right = feature.attribute('traffic_mode:right')
    traffic_mode_both = feature.attribute('traffic_mode:both')

    traffic_mode_left, traffic_mode_right = split_both_values_to_left_right(traffic_mode_both, traffic_mode_left, traffic_mode_right)

    parking_right = feature.attribute('parking:right')
    parking_left = feature.attribute('parking:left')
    parking_both = feature.attribute('parking:both')

    parking_left, parking_right = split_both_values_to_left_right(parking_both, parking_left, parking_right)

    side = feature.attribute('side')
    is_sidepath = feature.attribute('proc_sidepath')

    if not traffic_mode_left:
        traffic_mode_left = determine_traffic_mode_left(way_type, is_sidepath, side, parking_right, parking_left, traffic_mode_right)

    if not traffic_mode_right:
        traffic_mode_right = determine_traffic_mode_right(way_type, is_sidepath, side, parking_right, parking_left, traffic_mode_left)

    return traffic_mode_left, traffic_mode_right, data_missing


def determine_mandatory_use(feature, proc_oneway):
    proc_mandatory = NULL
    proc_traffic_sign = NULL

    bicycle = feature.attribute('bicycle')
    cycleway = feature.attribute('cycleway')
    cycleway_left = feature.attribute('cycleway:left')
    cycleway_right = feature.attribute('cycleway:right')
    cycleway_both = feature.attribute('cycleway:both')
    traffic_sign = feature.attribute('traffic_sign')
    way_type = feature.attribute('way_type')
    is_sidepath = feature.attribute('proc_sidepath')

    proc_traffic_sign = traffic_sign

    if way_type in ['bicycle road', 'shared road', 'shared traffic lane', 'track or service']:
    #if cycle lanes are present, mark center line as "use sidepath"
        if cycleway in ['lane', 'share_busway'] or cycleway_both in ['lane', 'share_busway'] or ('yes' in proc_oneway and cycleway_right in ['lane', 'share_busway']):
            proc_mandatory = 'use_sidepath'
        #if tracks are present, mark center line as "optional sidepath" - as well as if "bicycle" is explicitely tagged as "optional_sidepath"
        elif cycleway == 'track' or cycleway_both == 'track' or ('yes' in proc_oneway and cycleway_right == 'track'):
            proc_mandatory = 'optional_sidepath'
        if bicycle in ['use_sidepath', 'optional_sidepath']:
            proc_mandatory = bicycle
    elif is_sidepath == "yes":
        #derive mandatory use from the presence of traffic signs
        if traffic_sign:
            traffic_sign = d.getDelimitedValues(traffic_sign.replace(',', ';'), ';', 'string')
            traffic_sign_set = set(traffic_sign)

            proc_mandatory = 'no'  # Default value

            # Check for mandatory and not mandatory signs
            if traffic_sign_set & p.mandatory_traffic_sign_set:
                proc_mandatory = 'yes'
            elif traffic_sign_set & p.mandatory_traffic_sign_set:
                proc_mandatory = 'no'

    #mark cycle prohibitions
    highway = feature.attribute('highway')
    if highway in p.cycling_highway_prohibition_list or bicycle == 'no':
        proc_mandatory = 'prohibited'

    return proc_mandatory, proc_traffic_sign


def update_feature_attributes(layer, feature, field_ids):
    data_missing = []
    one_way = derive_oneway_status(feature)
    layer.changeAttributeValue(feature.id(), field_ids.get('proc_oneway'), one_way)

    proc_width, width_missing = calc_feature_width(feature, one_way)
    data_missing.extend(width_missing)
    layer.changeAttributeValue(feature.id(), field_ids.get("proc_width"), proc_width)

    proc_surface, surface_missing = derive_surface(feature)
    data_missing.extend(surface_missing)
    layer.changeAttributeValue(feature.id(), field_ids.get("proc_surface"), proc_surface)

    proc_smoothness, smoothness_missing = derive_smoothness(feature)
    data_missing.extend(smoothness_missing)
    layer.changeAttributeValue(feature.id(), field_ids.get("proc_smoothness"), proc_smoothness)

    right_hand_traffic = p.right_hand_traffic
    traffic_mode_left, traffic_mode_right, traffic_mode_missing = derive_traffic_modes(feature, right_hand_traffic=right_hand_traffic)
    data_missing.extend(traffic_mode_missing)
    layer.changeAttributeValue(feature.id(), field_ids.get("proc_traffic_mode_left"), traffic_mode_left)
    layer.changeAttributeValue(feature.id(), field_ids.get("proc_traffic_mode_right"), traffic_mode_right)
    
    proc_separation_left, proc_separation_right = determine_separation(feature, right_hand_traffic, traffic_mode_left, traffic_mode_right)
    layer.changeAttributeValue(feature.id(), field_ids.get("proc_separation_left"), proc_separation_left)
    layer.changeAttributeValue(feature.id(), field_ids.get("proc_separation_right"), proc_separation_right)
    
    proc_physical_buffer_left, proc_physical_buffer_right = determine_buffer(feature, right_hand_traffic, traffic_mode_left, traffic_mode_right)
    layer.changeAttributeValue(feature.id(), field_ids.get("proc_buffer_left"), proc_physical_buffer_left)
    layer.changeAttributeValue(feature.id(), field_ids.get("proc_buffer_right"), proc_physical_buffer_right)
    
    ## Extra Infos
    proc_mandatory, proc_traffic_sign = determine_mandatory_use(feature, one_way)
    layer.changeAttributeValue(feature.id(), field_ids.get("proc_mandatory"), proc_mandatory)
    layer.changeAttributeValue(feature.id(), field_ids.get("proc_traffic_sign"), proc_traffic_sign)
    
    #-------------
    #add extra attributes to easy filter non-usable segments or by way type
    #-------------

    filter_usable = 0 if proc_mandatory in ['prohibited', 'use_sidepath'] else 1
    layer.changeAttributeValue(feature.id(), field_ids['filter_usable'], filter_usable)
    
    # Determine filter_way_type value
    way_type_mapping = {
        'cycle path': 'separated',
        'cycle track': 'separated',
        'shared path': 'separated',
        'segregated path': 'separated',
        'shared footway': 'separated',
        'cycle lane (protected)': 'separated',
        'cycle lane (advisory)': 'cycle lanes',
        'cycle lane (exclusive)': 'cycle lanes',
        'cycle lane (central)': 'cycle lanes',
        'link': 'cycle lanes',
        'crossing': 'cycle lanes',
        'bicycle road': 'bicycle road',
        'shared road': 'shared traffic',
        'shared traffic lane': 'shared traffic',
        'shared bus lane': 'shared traffic',
        'track or service': 'shared traffic'
    }

    filter_way_type = way_type_mapping.get(feature.attribute('way_type'), None)
    layer.changeAttributeValue(feature.id(), field_ids.get('filter_way_type'), filter_way_type)

    for entry in data_missing:
        layer.changeAttributeValue(feature.id(), field_ids.get(entry), 1)
        
    return one_way, proc_width, proc_surface, proc_smoothness, traffic_mode_left, traffic_mode_right, proc_separation_left, proc_separation_right, proc_physical_buffer_left, proc_physical_buffer_right, proc_mandatory, proc_traffic_sign, data_missing  # Just returning for testing

def get_base_index(way_type, feature, data_bonus):
    base_index = p.base_index_dict.get(way_type, None)
    # On roads with restricted motor vehicle access, overwrite the base index with an access-specific base index
    if way_type in ['bicycle road', 'shared road', 'shared traffic lane', 'track or service']:
        motor_vehicle_access = d.getAccess(feature, 'motor_vehicle')
        base_index = p.motor_vehicle_access_index_dict.get(motor_vehicle_access, base_index)
        if motor_vehicle_access in p.motor_vehicle_access_index_dict:
            data_bonus.append('motor vehicle restricted')
    return base_index

def calculate_width(way_type, proc_width, proc_oneway, feature):
    is_dedicated_for_cycling = way_type not in ['bicycle road', 'shared road', 'shared traffic lane', 'shared bus lane', 'track or service'] or d.getAccess(feature, 'motor_vehicle') == 'no'
    calc_width = proc_width
    minimum_factor = 0

    if is_dedicated_for_cycling:
        if calc_width and 'yes' not in proc_oneway:
            calc_width /= 1.6
    else:
        minimum_factor = 0.25
        if calc_width:
            if way_type == 'shared traffic lane':
                calc_width = max(calc_width - 2 + ((4.5 - calc_width) / 3), 0)
            elif way_type == 'shared bus lane':
                calc_width = max(calc_width - 3 + ((5.5 - calc_width) / 3), 0)
            else:
                if 'yes' not in proc_oneway:
                    calc_width /= 1.6
                calc_width -= 2

    return calc_width, minimum_factor

def calculate_width_factor(calc_width, minimum_factor, way_type, motor_vehicle_access):
    if calc_width:
        calc_width = max(0.001, calc_width)
        if calc_width <= 3 or way_type in ['bicycle road', 'shared road', 'shared traffic lane', 'shared bus lane', 'track or service']:
            fac_width = 1.1 / (1 + 20 * math.e ** (-2.1 * calc_width))
        else:
            fac_width = 2 / (1 + 1.8 * math.e ** (-0.24 * calc_width))

        if way_type in ['bicycle road', 'shared road', 'shared traffic lane', 'track or service'] and motor_vehicle_access in p.motor_vehicle_access_index_dict:
            fac_width = fac_width + ((1 - fac_width) / 2)

        return round(fac_width, 3)
    return None


def add_width_bonus_or_malus(fac_width, data_bonus, data_malus):
    if fac_width is None:
        return
    if fac_width > 1:
        data_bonus = data_bonus.append('wide width')
    if fac_width and fac_width <= 0.5:
        data_malus = data_malus.append('narrow width')


def calculate_surface_factor(proc_smoothness, proc_surface):
    fac_surface = p.smoothness_factor_dict.get(proc_smoothness, None)
    if fac_surface is None:
        fac_surface = p.surface_factor_dict.get(proc_surface, None)
    return fac_surface


def add_surface_bonus_or_malus(fac_surface, data_bonus, data_malus):
    if fac_surface and fac_surface > 1:
        data_bonus = data_bonus.append('excellent surface')
    if fac_surface and fac_surface <= 0.5:
        data_malus = data_malus.append('bad surface')

def calculate_maxspeed_factor(proc_maxspeed):
    fac_maxspeed = 1
    if proc_maxspeed:
        for maxspeed in sorted(p.maxspeed_factor_dict.keys(), reverse=True):
            if proc_maxspeed >= maxspeed:
                fac_maxspeed = p.maxspeed_factor_dict[maxspeed]
                break
    return fac_maxspeed

def is_max_speed_missing(way_type, proc_highway, proc_sidepath, proc_maxspeed):
    if proc_maxspeed is None and way_type != 'track or service' and proc_sidepath != 'no' and proc_highway not in ['pedestrian', 'service', 'track']:
        return True
    return False

def calculate_highway_factor(proc_highway):
    return p.highway_factor_dict.get(proc_highway, 1)


def calculate_surface_width_factor(fac_width, fac_surface):
    if fac_width and fac_surface:
        weight_factor_width = max(1 - fac_width, 0) + 0.5
        weight_factor_surface = max(1 - fac_surface, 0) + 0.5
        fac_1 = (weight_factor_width * fac_width + weight_factor_surface * fac_surface) / (weight_factor_width + weight_factor_surface)
    elif fac_width:
        fac_1 = fac_width
    elif fac_surface:
        fac_1 = fac_surface
    else:
        fac_1 = 1
    return round(fac_1, 2)


def calculate_highway_and_maxspeed_factor(way_type, fac_highway, fac_maxspeed, is_sidepath):
    weight = p.highway_factor_dict_weights.get(way_type, 1)
    if way_type in ['shared path', 'segregated path', 'shared footway'] and is_sidepath != 'yes':
        weight = 0
    fac_2 = fac_highway * fac_maxspeed
    fac_2 = fac_2 + ((1 - fac_2) * (1 - weight))
    if not fac_2:
        fac_2 = 1
    return round(fac_2, 2), weight


def apply_shared_lane_markings_bonus(way_type, fac_4, cycleway, cycleway_both, cycleway_left, cycleway_right, data_bonus):
    #bonus for sharrows/cycleway=shared lane markings
    if way_type in ['shared road', 'shared traffic lane']:
        if cycleway == 'shared_lane' or cycleway_both == 'shared_lane' or cycleway_left == 'shared_lane' or cycleway_right == 'shared_lane':
            fac_4 += 0.1
            data_bonus.append('shared lane markings')
    return fac_4

def apply_surface_color_bonus(way_type, fac_4, feature, is_sidepath, data_bonus):
    #bonus for surface colour on shared traffic ways
    if 'cycle lane' in way_type or way_type in ['crossing', 'shared bus lane', 'link', 'bicycle road'] or (way_type in ['shared path', 'segregated path'] and is_sidepath == 'yes'):
        surface_colour = feature.attribute('surface:colour')
        if surface_colour and surface_colour not in ['no', 'none', 'grey', 'gray', 'black']:
            if way_type == 'crossing':
                fac_4 += 0.15 #more bonus for coloured crossings
            else:
                fac_4 += 0.05
            data_bonus.append('surface colour')
    return fac_4

def apply_marked_crossing_bonus(way_type, fac_4, feature, data_bonus, data_missing):
    #bonus for marked or signalled crossings
    if way_type == 'crossing':
        crossing = feature.attribute('crossing')
        if not crossing:
            data_missing.append('crossing')
        crossing_markings = feature.attribute('crossing:markings')
        if not crossing_markings:
            data_missing.append('crossing_markings')
        if crossing in ['traffic_signals']:
            fac_4 += 0.2
            data_bonus.append('signalled crossing')
        elif crossing in ['marked', 'zebra'] or (crossing_markings and crossing_markings != 'no'):
            fac_4 += 0.1
            data_bonus.append('marked crossing')
    return fac_4

def apply_missing_streetlight_malus(fac_4, feature, data_malus, data_missing):
    #malus for missing street light
    lit = feature.attribute('lit')
    if not lit:
        data_missing.append('lit')
    if lit == 'no':
        fac_4 -= 0.1
        data_malus.append('no street lighting')
    return fac_4

def apply_no_parking_buffer_malus(way_type, fac_4, traffic_mode_left, buffer_left, traffic_mode_right, buffer_right, is_sidepath, data_malus):
    #malus for cycle way along parking without buffer (danger of dooring)
    #TODO: currently no information if parking is parallel parking - for this, a parking orientation lookup on the centerline is needed for separately mapped cycle ways
    if ((traffic_mode_left == 'parking' and buffer_left and buffer_left < 1) or (traffic_mode_right == 'parking' and buffer_right and buffer_right < 1)) and ('cycle lane' in way_type or (way_type in ['cycle track', 'shared path', 'segregated path'] and is_sidepath == 'yes')):
        #malus is 0 (buffer = 1m) .. 0.2 (buffer = 0m)
        diff = 0
        if traffic_mode_left == 'parking':
            diff = abs(buffer_left - 1) / 5
        if traffic_mode_right == 'parking':
            diff = abs(buffer_right - 1) / 5
        if traffic_mode_left == 'parking' and traffic_mode_right == 'parking':
            diff = abs(((buffer_left + buffer_right) / 2) - 1) / 5
        fac_4 -= diff
        data_malus.append(data_malus, 'insufficient dooring buffer')
        
    return fac_4

def apply_permissive_bicycle_malus(bicycle, fac_4, data_malus):
    #malus if bicycle is only "permissive"
    if bicycle == 'permissive':
        fac_4 -= 0.2
        data_malus.append(data_malus, 'cycling not intended')
    return fac_4

def calculate_level_of_traffic_stress(way_type, proc_oneway, proc_width, proc_maxspeed, proc_highway, feature):
    lts = NULL
    if way_type in ['cycle path', 'cycle track', 'segregated path', 'cycle lane (protected)']:
        lts = 1
    elif way_type in ['shared path', 'shared footway']:
        if not proc_oneway in ['yes', '-1'] and proc_width and proc_width < 3 and proc_maxspeed and proc_maxspeed > 30:
            lts = 3
        else:
            lts = 1
    elif way_type in ['cycle lane (advisory)', 'cycle lane (central)', 'shared bus lane', 'link', 'crossing']:
        if proc_maxspeed and proc_maxspeed <= 10:
            lts = 1
        elif proc_maxspeed and proc_maxspeed <= 30:
            lts = 2
        elif proc_width and proc_width >= 1.5:
            lts = 3
        else:
            lts = 4
    elif way_type == 'cycle lane (exclusive)':
        if proc_maxspeed and proc_maxspeed <= 10:
            lts = 1
        elif proc_maxspeed and proc_maxspeed <= 50 and proc_width and proc_width >= 1.85:
            lts = 2
        else:
            lts = 3
    elif way_type in ['bicycle road', 'shared road', 'shared traffic lane']:
        if way_type == 'bicycle road' and d.getAccess(feature, 'motor_vehicle') in p.motor_vehicle_access_index_dict:
            lts = 1
        else:
            priority_road = feature.attribute('priority_road')
            if proc_maxspeed and proc_maxspeed <= 10 and proc_highway in ['residential', 'living_street'] and (not priority_road or priority_road == 'no'):
                lts = 1
            elif proc_maxspeed and proc_maxspeed <= 30 and proc_highway in ['tertiary', 'tertiary_link', 'unclassified', 'road', 'residential', 'living_street']:
                lts = 2
            else:
                lts = 4
    elif way_type == 'track or service':
        if proc_maxspeed and proc_maxspeed <= 10:
            lts = 1
        else:
            lts = 2
    return lts

print_timestamped_message('Start processing:')
print_timestamped_message('Read data...')



#--------------------------------
#      S c r i p t   S t a r t
#--------------------------------
def main():
    if not exists(dir_input + file_format):
        if multi_input:
            print(time.strftime('%H:%M:%S', time.localtime()), '[!] Error: No valid input files at "' + dir_input + '*' + file_format + '".')
        else:
            print(time.strftime('%H:%M:%S', time.localtime()), '[!] Error: No valid input file at "' + dir_input + file_format + '".')
        return False

    layer_way_input = QgsVectorLayer(dir_input + file_format + '|geometrytype=LineString', 'way input', 'ogr')

    layer = reproject_layer(layer_way_input, p.crs_metric)
    layer = retain_fields(layer, p.attributes_list)

    for attr in new_attributes_dict.keys():
        p.attributes_list.append(attr)

    ensure_attributes(layer, p.attributes_list, new_attributes_dict)
    # Index fields for faster access
    field_ids = {field.name(): layer.fields().indexOf(field.name()) for field in layer.fields()}
    # Add the layer to the project
    QgsProject.instance().addMapLayer(layer, False)


    #---------------------------------------------------------------#
    #1: Check paths whether they are sidepath (a path along a road) #
    #---------------------------------------------------------------#

    print_timestamped_message('Sidepath check...')
    print_timestamped_message('   Create way layers...')
    
    # Create path and road layers
    layer_path = processing.run('qgis:extractbyexpression', {
        'INPUT': layer,
        # 'EXPRESSION': '"highway" IN (\'cycleway\', \'footway\', \'path\', \'bridleway\', \'steps\')',
        'EXPRESSION': '"highway" IS \'cycleway\' OR "highway" IS \'footway\' OR "highway" IS \'path\' OR "highway" IS \'bridleway\' OR "highway" IS \'steps\'',
        'OUTPUT': 'memory:'
    })['OUTPUT']

    layer_roads = processing.run('qgis:extractbyexpression', {
        'INPUT': layer,
        # 'EXPRESSION': '"highway" NOT IN (\'cycleway\', \'footway\', \'path\', \'bridleway\', \'steps\', \'track\')',
        'EXPRESSION': '"highway" IS NOT \'cycleway\' AND "highway" IS NOT \'footway\' AND "highway" IS NOT \'path\' AND "highway" IS NOT \'bridleway\' AND "highway" IS NOT \'steps\' AND "highway" IS NOT \'track\'',
        'OUTPUT': 'memory:'
    })['OUTPUT']

    print_timestamped_message('   Create check points...')

    layer_path_points = processing.run('native:pointsalonglines', {
        'INPUT': layer_path,
        'DISTANCE': p.sidepath_buffer_distance,
        'OUTPUT': 'memory:'
    })['OUTPUT']

    layer_path_points_endpoints = processing.run('native:extractspecificvertices', {
        'INPUT': layer_path,
        'VERTICES': '-1',
        'OUTPUT': 'memory:'
    })['OUTPUT']

    layer_path_points = processing.run('native:mergevectorlayers', {
        'LAYERS': [layer_path_points, layer_path_points_endpoints],
        'OUTPUT': 'memory:'
    })['OUTPUT']

    layer_path_points_buffers = processing.run('native:buffer', {
        'INPUT': layer_path_points,
        'DISTANCE': p.sidepath_buffer_size,
        'OUTPUT': 'memory:'
    })['OUTPUT']

    QgsProject.instance().addMapLayer(layer_path_points_buffers, False)
    
    print_timestamped_message('   Check for adjacent roads...')

    # Check for adjacent roads and save information in a dictionary
    sidepath_dict = {}
    for buffer in layer_path_points_buffers.getFeatures():
        buffer_id = buffer.attribute('id')
        buffer_layer = buffer.attribute('layer')
        if not buffer_id in sidepath_dict:
            sidepath_dict[buffer_id] = {
                'checks': 1,
                'id': {},
                'highway': {},
                'name': {},
                'maxspeed': {}
            }
        else:
            sidepath_dict[buffer_id]['checks'] += 1 # FIXME: what is this for?

        layer_path_points_buffers.removeSelection()
        layer_path_points_buffers.select(buffer.id())

        processing.run('native:selectbylocation', {
            'INPUT': layer_roads,
            'INTERSECT': QgsProcessingFeatureSourceDefinition(layer_path_points_buffers.id(), selectedFeaturesOnly=True),
            'METHOD': 0,
            'PREDICATE': [0, 6]
        })

        ids_list = []
        highway_list = []
        name_list = []
        maxspeed_dict = {}
        
        for road in layer_roads.selectedFeatures():
            road_layer = road.attribute('layer')
            if buffer_layer != road_layer:
                continue #only consider geometries in the same layer
            road_id = road.attribute('id')
            road_highway = road.attribute('highway')
            road_name = road.attribute('name')
            road_maxspeed = d.getNumber(road.attribute('maxspeed'))

            if road_id not in ids_list:
                ids_list.append(road_id)
            if road_highway not in highway_list:
                highway_list.append(road_highway)
            if road_highway not in maxspeed_dict or maxspeed_dict[road_highway] < road_maxspeed:
                maxspeed_dict[road_highway] = road_maxspeed
            if road_name not in name_list:
                name_list.append(road_name)
        
        for road_id in ids_list:
            sidepath_dict[buffer_id]['id'][road_id] = sidepath_dict[buffer_id]['id'].get(road_id, 1) + 1
        for road_highway in highway_list:
            sidepath_dict[buffer_id]['highway'][road_highway] = sidepath_dict[buffer_id]['highway'].get(road_highway, 1) + 1
        for road_name in name_list:
            sidepath_dict[buffer_id]['name'][road_name] = sidepath_dict[buffer_id]['name'].get(road_name, 1) + 1
        for highway in maxspeed_dict.keys():
            if highway not in sidepath_dict[buffer_id]['maxspeed'] or sidepath_dict[buffer_id]['maxspeed'][highway] < maxspeed_dict[highway]:
                sidepath_dict[buffer_id]['maxspeed'][highway] = maxspeed_dict[highway]

    highway_class_list = ['motorway', 'motorway_link', 'trunk', 'trunk_link', 'primary', 'primary_link', 'secondary', 'secondary_link', 'tertiary', 'tertiary_link', 'unclassified', 'residential', 'road', 'living_street', 'service', 'pedestrian', NULL]

    update_sidepath_attributes(layer, sidepath_dict, field_ids, highway_class_list)


    #-------------------------------------------------------------------------------#
    #2: Split and shift attributes/geometries for sidepath mapped on the centerline #
    #-------------------------------------------------------------------------------#

    print_timestamped_message('Split line bundles...')
    update_offset_attributes(layer, field_ids, p)
    
    update_offset_layer_attributes(layer, field_ids, qgis_layers, d)
    #TODO: Attribute mit "both" auf left und right aufteilen?

    #TODO: clean up offset layers
    merge_layers(layer, qgis_layers)

    #--------------------------------------------#
    #3: Determine way type for every way segment #
    #--------------------------------------------#

    print_timestamped_message('Determine way type...')
    update_way_type(layer, field_ids=field_ids)

    #----------------------------------------------------#
    #4: Derive relevant attributes for index and factors #
    #----------------------------------------------------#
    
    print_timestamped_message('Derive attributes/calculate index...')

    # update_way_attributes(layer, field_ids)
    with edit(layer):
        for feature in layer.getFeatures():
            proc_oneway, proc_width, proc_surface, proc_smoothness, traffic_mode_left, traffic_mode_right, proc_separation_left, proc_separation_right, buffer_left, buffer_right, proc_mandatory, proc_traffic_sign, data_missing = update_feature_attributes(layer, feature, field_ids)

            way_type = feature.attribute('way_type')
            side = feature.attribute('side')
            is_sidepath = feature.attribute('proc_sidepath')
            cycleway = feature.attribute('cycleway')
            cycleway_both = feature.attribute('cycleway:both')
            cycleway_left = feature.attribute('cycleway:left')
            cycleway_right = feature.attribute('cycleway:right')
            bicycle = feature.attribute('bicycle')


            #-------------------------------#
            #5: Calculate index and factors #
            #-------------------------------#

            #human readable strings for significant good or bad factors
            data_bonus = []
            data_malus = []
            #------------------------------------
            #Set base index according to way type
            #------------------------------------
            base_index = get_base_index(way_type, feature, data_bonus)
            layer.changeAttributeValue(feature.id(), field_ids.get('base_index'), base_index)

            #--------------------------------------------
            #Calculate width factor according to way type
            #--------------------------------------------
            calc_width, minimum_factor = calculate_width(way_type, proc_width, proc_oneway, feature)
            fac_width = calculate_width_factor(calc_width, minimum_factor, way_type, d.getAccess(feature, 'motor_vehicle'))
            add_width_bonus_or_malus(fac_width, data_bonus, data_malus)

            #---------------------------------------
            #Calculate surface and smoothness factor
            #---------------------------------------
            fac_surface = calculate_surface_factor(proc_smoothness, proc_surface)
            layer.changeAttributeValue(feature.id(), field_ids.get('fac_surface'), fac_surface)
            add_surface_bonus_or_malus(fac_surface, data_bonus, data_malus)

            #------------------------------------------------
            #Calculate highway (sidepath) and maxspeed factor
            #------------------------------------------------
            proc_highway = feature.attribute('proc_highway')
            proc_maxspeed = feature.attribute('proc_maxspeed')
            proc_sidepath = feature.attribute('proc_sidepath')

            fac_highway = calculate_highway_factor(proc_highway)
            fac_maxspeed = calculate_maxspeed_factor(proc_maxspeed)

            layer.changeAttributeValue(feature.id(), field_ids.get('fac_highway'), fac_highway)
            layer.changeAttributeValue(feature.id(), field_ids.get('fac_maxspeed'), fac_maxspeed)

            if is_max_speed_missing(way_type, proc_highway, proc_sidepath, proc_maxspeed):
                data_missing.append('maxspeed')
                layer.changeAttributeValue(feature.id(), field_ids.get('data_missing_maxspeed'), 1)

#            #-------------------------------------------------
#            #Calculate (physical) separation and buffer factor
#            #-------------------------------------------------
#            if is_sidepath == 'yes' and (traffic_mode_left or traffic_mode_right): #only for sidepath geometries
#                #get the "strongest" separation value for each side and derive a protection level from that
#                prot_level_separation_left = 0
#                if separation_left:
#                    separation_left = d.getDelimitedValues(separation_left, ';', 'string')
#                    for separation in separation_left:
#                        prot_level = p.separation_level_dict['ELSE']
#                        if separation in p.separation_level_dict:
#                            prot_level = p.separation_level_dict[separation]
#                        prot_level_separation_left = max(prot_level_separation_left, prot_level)
#                prot_level_separation_right = 0
#                if separation_right:
#                    separation_right = d.getDelimitedValues(separation_right, ';', 'string')
#                    for separation in separation_right:
#                        prot_level = p.separation_level_dict['ELSE']
#                        if separation in p.separation_level_dict:
#                            prot_level = p.separation_level_dict[separation]
#                        prot_level_separation_right = max(prot_level_separation_right, prot_level)
#
#                #derive protection level indicated by a buffer zone (a value from 0 to 1, half of the buffer width)
#                prot_level_buffer_left = min(buffer_left / 2, 1)
#                prot_level_buffer_right = min(buffer_right / 2, 1)
#
#                #derive a total protection level per side (separation has a stronger weight, because it results in more (perception of) safeness)
#                prot_level_left = prot_level_separation_left * 0.67 + prot_level_buffer_left * 0.33
#                prot_level_right = prot_level_separation_right * 0.67 + prot_level_buffer_right * 0.33
#
#                layer.changeAttributeValue(feature.id(), field_ids.get('prot_level_separation_left'), round(prot_level_separation_left, 3))
#                layer.changeAttributeValue(feature.id(), field_ids.get('prot_level_separation_right'), round(prot_level_separation_right, 3))
#                layer.changeAttributeValue(feature.id(), field_ids.get('prot_level_buffer_left'), round(prot_level_buffer_left, 3))
#                layer.changeAttributeValue(feature.id(), field_ids.get('prot_level_buffer_right'), round(prot_level_buffer_right, 3))
#                layer.changeAttributeValue(feature.id(), field_ids.get('prot_level_left'), round(prot_level_left, 3))
#                layer.changeAttributeValue(feature.id(), field_ids.get('prot_level_right'), round(prot_level_right, 3))
#
#                #derive a factor from that protection level values (0.9: no protection, 1.4: high protection)
#                #if there is motor vehicle traffic on one side and foot (or bicycle) traffic on the other, the factor is composed of 75% motor vehicle side and 25% of the other side.
#                if traffic_mode_left in ['motor_vehicle', 'psv', 'parking'] and traffic_mode_right in ['foot', 'bicycle']:
#                    prot_level = prot_level_left * 0.75 + prot_level_right * 0.25
#                if traffic_mode_left in ['foot', 'bicycle'] and traffic_mode_right in ['motor_vehicle', 'psv', 'parking']:
#                    prot_level = prot_level_left * 0.25 + prot_level_right * 0.75
#                #same traffic mode on both sides: protection level is the average of both sides levels
#                if (traffic_mode_left in ['motor_vehicle', 'psv', 'parking'] and traffic_mode_right in ['motor_vehicle', 'psv', 'parking']) or (traffic_mode_left in ['foot', 'bicycle'] and traffic_mode_right in ['foot', 'bicycle']):
#                    prot_level = (prot_level_left + prot_level_right) / 2
#                #no traffic on a side: only the other side with traffic counts.
#                if traffic_mode_right == 'no' and traffic_mode_left != 'no':
#                    prot_level = prot_level_left
#                if traffic_mode_left == 'no' and traffic_mode_right != 'no':
#                    prot_level = prot_level_right
#
#                fac_protection_level = 0.9 + prot_level / 2
#                #no motor vehicle traffic? Factor is only half weighted
#                if traffic_mode_left not in ['motor_vehicle', 'psv', 'parking'] and traffic_mode_right not in ['motor_vehicle', 'psv', 'parking']:
#                    fac_protection_level -= (fac_protection_level - 1) / 2
#                fac_protection_level = round(fac_protection_level, 3)
#            else:
#                fac_protection_level = NULL
#
#            layer.changeAttributeValue(feature.id(), field_ids.get('fac_protection_level'), fac_protection_level)



            #---------------
            #Calculate index
            #---------------
            index = NULL
            index_10 = NULL
            if base_index != NULL:
                
                fac_1 = calculate_surface_width_factor(fac_width, fac_surface)
                layer.changeAttributeValue(feature.id(), field_ids.get('fac_1'), round(fac_1, 2))

                fac_2, weight = calculate_highway_and_maxspeed_factor(way_type, fac_highway, fac_maxspeed, is_sidepath)
                layer.changeAttributeValue(feature.id(), field_ids.get('fac_2'), round(fac_2, 2))

                if weight >= 0.5:
                    if fac_2 > 1:
                        data_bonus.append('slow traffic')
                    if fac_highway <= 0.7:
                        data_malus.append('along a major road')
                    if fac_maxspeed <= 0.7:
                        data_malus.append('along a road with high speed limits')

                #factor 3: separation and buffer
                fac_3 = 1
                layer.changeAttributeValue(feature.id(), field_ids.get('fac_3'), round(fac_3, 2))

                #factor group 4: miscellaneous attributes can result in an other bonus or malus
                fac_4 = 1
                fac_4 = apply_shared_lane_markings_bonus(way_type, fac_4, cycleway, cycleway_both, cycleway_left, cycleway_right, data_bonus)
                fac_4 = apply_surface_color_bonus(way_type, fac_4, feature, is_sidepath, data_bonus)
                fac_4 = apply_marked_crossing_bonus(way_type, fac_4, feature, data_bonus, data_missing)
                fac_4 = apply_missing_streetlight_malus(fac_4, feature, data_malus, data_missing)
                fac_4 = apply_no_parking_buffer_malus(way_type, fac_4, traffic_mode_left, buffer_left, traffic_mode_right, buffer_right, is_sidepath, data_malus)
                fac_4 = apply_permissive_bicycle_malus(bicycle, fac_4, data_malus)


                if "lit" in data_missing:
                    layer.changeAttributeValue(feature.id(), field_ids.get('data_missing_lit'), 1)

                layer.changeAttributeValue(feature.id(), field_ids.get('fac_4'), round(fac_4, 2))

                index = base_index * fac_1 * fac_2 * fac_3 * fac_4

                index = max(min(100, index), 0) #index should be between 0 and 100 in the end for pragmatic reasons
                index = int(round(index))       #index is an int

                index_10 = index // 10   #index from 0..10 (e.g. index = 56 -> index_10 = 5)

            layer.changeAttributeValue(feature.id(), field_ids.get('index'), index)
            layer.changeAttributeValue(feature.id(), field_ids.get('index_10'), index_10)
            layer.changeAttributeValue(feature.id(), field_ids.get('data_missing'), ';'.join(data_missing))
            layer.changeAttributeValue(feature.id(), field_ids.get('data_bonus'), ";".join(data_bonus))
            layer.changeAttributeValue(feature.id(), field_ids.get('data_malus'), ";".join(data_malus))

            #---------------
            #Calculate levels of traffic stress
            #---------------
            lts = calculate_level_of_traffic_stress(way_type, proc_oneway, proc_width, proc_maxspeed, proc_highway, feature)
            layer.changeAttributeValue(feature.id(), field_ids.get('stress_level'), lts)

            #---------------
            #derive a data completeness number
            #---------------
            data_incompleteness = 0
            for missing_data in data_missing:
                data_incompleteness += p.data_incompleteness_dict.get(missing_data, 0)
            layer.changeAttributeValue(feature.id(), field_ids.get('data_incompleteness'), data_incompleteness)

        layer.updateFields()

    #clean up data set and reproject to output crs
    print(time.strftime('%H:%M:%S', time.localtime()), 'Clean up data...')
    layer = processing.run('native:retainfields', { 'INPUT' : layer, 'FIELDS' : p.attributes_list_finally_retained, 'OUTPUT': 'memory:' })['OUTPUT']
    layer = processing.run('native:reprojectlayer', { 'INPUT' : layer, 'TARGET_CRS' : QgsCoordinateReferenceSystem(p.crs_output), 'OUTPUT': 'memory:'})['OUTPUT']

    print(time.strftime('%H:%M:%S', time.localtime()), 'Save output data set...')
    qgis.core.QgsVectorFileWriter.writeAsVectorFormat(layer, dir_output + file_format, 'utf-8', QgsCoordinateReferenceSystem(p.crs_output), 'GeoJSON')

    print(time.strftime('%H:%M:%S', time.localtime()), 'Display data...')
    QgsProject.instance().addMapLayer(layer, True)
    layer.setName('Cycling Quality Index')
    layer.loadNamedStyle(project_dir + 'styles/index.qml')
    #focus on output layer
    iface.mapCanvas().setExtent(layer.extent())


#multiple input files can be merged to one single input
if multi_input:
    input_data = []
    i = 1
    while exists(dir_input + str(i) + file_format):
        print(time.strftime('%H:%M:%S', time.localtime()), '   Read input file ' + str(i) + '...')
        layer_way_input = QgsVectorLayer(dir_input + str(i) + file_format + '|geometrytype=LineString', 'way input', 'ogr')
        layer_way_input = processing.run('native:retainfields', { 'INPUT' : layer_way_input, 'FIELDS' : p.attributes_list, 'OUTPUT': 'memory:'})['OUTPUT']
        input_data.append(layer_way_input)
        i += 1
    if input_data:
        print(time.strftime('%H:%M:%S', time.localtime()), '   Merge input files...')
        layer_way_input = processing.run('native:mergevectorlayers', { 'LAYERS' : input_data, 'OUTPUT': 'memory:'})['OUTPUT']
        layer_way_input = processing.run('native:deleteduplicategeometries', {'INPUT': layer_way_input, 'OUTPUT': dir_input + file_format })
    else:
        print(time.strftime('%H:%M:%S', time.localtime()), '[!] Warning: No valid input files at "' + dir_input + '*' + file_format + '". Use ascending numbers starting with 1 at the end of the file names.')
        if exists(dir_input + file_format):
            print(time.strftime('%H:%M:%S', time.localtime()), '[!] Warning: Continuing with input file "' + dir_input + file_format + '".')

main()

print(time.strftime('%H:%M:%S', time.localtime()), 'Finished processing.')
