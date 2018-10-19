"""Work with Google APIs."""

from __future__ import absolute_import

import httplib
import json
import logging
import pprint
import socket
import time
import urllib
import urllib2

import attr

API_KEY = 'AIzaSyD5ahcNNKsmB1iB5ldI6HXV8BaWCv66tpo'
DIRECTIONS_BASE_URL = 'https://maps.googleapis.com/maps/api/directions/json'
GEOCODE_BASE_URL = 'https://maps.googleapis.com/maps/api/geocode/json'


class Error(Exception):
    """Base module exception."""


class ApiQueryLimitError(Error):
    """API called too often."""


class NetworkError(Error):
    """Generic network issue."""


@attr.s  # pylint: disable=missing-docstring,too-few-public-methods
class Directions(object):
    begin_latlng = attr.ib()
    end_latlng = attr.ib()
    duration = attr.ib()
    polyline = attr.ib()
    mode = attr.ib()


def directions(origin, destination, mode):
    """Get directions from origin to destination."""
    args = {
        'origin': origin,
        'destination': destination,
        'mode': mode,
    }
    result = _call_api(DIRECTIONS_BASE_URL, args)
    if result['status'] == 'ZERO_RESULTS':
        # Need to fake it -- sometimes gmaps just cannot figure it out
        # On the other hand, don't worry about it until we see a failure
        raise Error('Zero results: %s' % pprint.pformat(args))

    leg_data = result['routes'][0]['legs'][0]
    answer = Directions(
        begin_latlng='{lat},{lng}'.format(**leg_data['start_location']),
        end_latlng='{lat},{lng}'.format(**leg_data['end_location']),
        duration=leg_data['duration']['value'],
        polyline=result['routes'][0]['overview_polyline']['points'],
        mode=mode
    )  # yapf: disable
    return answer


def latlng_to_address(latlng, **args):
    """Get a textual address for a specific location."""
    args.update({
        'latlng': latlng,
    })  # yapf: disable
    answer = 'No known street address'
    result = _call_api(GEOCODE_BASE_URL, args)
    for entry in result['results']:
        if 'street_address' in entry['types']:
            print 'found street_address', entry['formatted_address']
            answer = entry['formatted_address']
    return answer


def encode_polyline(coords):
    """Turn coordinates into a string.

  https://developers.google.com/maps/documentation/utilities/polylinealgorithm

  Args:
    coords: seq of lat,lng coordinates

  Returns:
    string, encoding the coordinates
  """

    def _flatten(points):
        olat = 0
        olng = 0
        for point in points:
            lat = int(point[0] * 1e5)
            lng = int(point[1] * 1e5)
            yield lat - olat
            yield lng - olng
            olat, olng = lat, lng

    encoding = list()
    for num in _flatten(coords):
        num <<= 1
        if num < 0:
            num = ~num

        while num:
            encoding.append(num % 32 + 32 + 63)
            num >>= 5
        encoding[-1] -= 32

    return ''.join([chr(x) for x in encoding])


def decode_polyline(polyline):
    """Turn strings into a coordinates.

  https://developers.google.com/maps/documentation/utilities/polylinealgorithm

  Args:
    polyline: string, encoding the coordinates

  Returns:
    coords: seq of lat,lng coordinates
  """

    def _decoder(encoded_string):
        """Base64 decoder without padding concerns."""
        num = 0
        count = 0
        for deci in (ord(q) - 63 for q in encoded_string):
            num += ((deci % 32) << (count * 5))
            count += 1
            if deci < 32:
                if num % 2:
                    num = -num
                num >>= 1
                yield num
                num = 0
                count = 0
        if num:
            yield num

    results = []
    point = (0, 0)
    for index, value in enumerate(_decoder(polyline)):
        if index % 2:
            point = (point[0], point[1] + value)
            results.append((point[0] / 1e5, point[1] / 1e5))
        else:
            point = (point[0] + value, point[1])
    return results


# test_coords = ((38.5, -120.2), (40.7, -120.95), (43.252, -126.453))
# expected = '_p~iF~ps|U_ulLnnqC_mqNvxq`@'
# actual = encode_google_polyline(test_coords)
# assert(expected == actual)

# test_string = 'u{~vFvyys@fS]'
# expected = [(40.63179, -8.65708), (40.62855, -8.65693)]
# actual = decode_google_polyline(test_string)
# assert(expected == actual)


def _call_api(base_url, parameters):
    """Make a generic call to a Google API.

    This routine was originally written specificaly for the maps API,
    so take care if used for anything else.
    """
    parameters['key'] = API_KEY
    url = base_url + '?' + urllib.urlencode(parameters)
    attempts = 0
    success = False
    while not success and attempts < 3:
        attempts += 1
        try:
            response_data = urllib2.urlopen(url, timeout=30).read()
            result = json.loads(response_data)
        except (ValueError, urllib2.URLError, httplib.BadStatusLine,
                socket.error) as err:
            result = {'error_message': str(err), 'status': 'NOTOK'}
        success = result['status'] in ('OK', 'ZERO_RESULTS')
        if not success:
            logging.info('sleeping because %(error_message)s', result)
            time.sleep(5.1)

    if result['status'] == 'OK':
        return result
    elif result['status'] == 'ZERO_RESULTS':
        print 'strange results:'
        pprint.pprint(result)
        return result
    elif result['status'] == 'NOTOK':
        raise NetworkError(result)
    elif result['status'] == 'OVER_QUERY_LIMIT':
        raise ApiQueryLimitError(result)
    else:
        raise Error(result)
