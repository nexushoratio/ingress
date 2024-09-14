"""Work with Google APIs."""

import dataclasses
import http.client
import json
import logging
import os
import pprint
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

import attr

API_KEY = os.getenv('GOOGLE_API_KEY', default='TBD')
REAL_DIRECTIONS_BASE_URL = (
    'https://maps.googleapis.com/maps/api/directions/json')
FAKE_DIRECTIONS_BASE_URL = (
    'https://script.google.com/macros/s'
    '/AKfycbzz6mcFX79LS2HAB6JmWtFfOqV-lWjI4WqPHbdH8W6_kG8ZkcE0/exec')
DIRECTIONS_BASE_URL = FAKE_DIRECTIONS_BASE_URL
GEOCODE_BASE_URL = 'https://maps.googleapis.com/maps/api/geocode/json'

LOCATION_TYPE_SCORES = {
    'ROOFTOP': 0,
    'RANGE_INTERPOLATED': 1,
    'GEOMETRIC_CENTER': 2,
    'APPROXIMATE': 3,
    'PLUS': 90,
    'UNKNOWN': 99,
}

PLUS_CODE_SCORES = {
    'compound_code': 0,
    'global_code': 1,
}


class Error(Exception):
    """Base module exception."""


class ApiQueryLimitError(Error):
    """API called too often."""


class NetworkError(Error):
    """Generic network issue."""


@dataclasses.dataclass(kw_only=True, order=True, frozen=True)
class AddressTypeValue:
    """A particular value returned from the Maps API."""
    typ: str
    val: str


@dataclasses.dataclass(kw_only=True, frozen=True)
class AddressDetails:
    """Address details."""
    address: str
    type_values: set[AddressTypeValue]


@attr.s
class Directions:  # pylint: disable=missing-docstring,too-few-public-methods
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
        raise Error(f'Zero results: {pprint.pformat(args)}')

    leg_data = result['routes'][0]['legs'][0]
    start = leg_data['start_location']
    end = leg_data['start_location']
    answer = Directions(
        begin_latlng=f'{start.lat},{start.lng}',
        end_latlng=f'{end.lat},{end.lng}',
        duration=leg_data['duration']['value'],
        polyline=result['routes'][0]['overview_polyline']['points'],
        mode=mode
    )  # yapf: disable
    return answer


def latlng_to_address(latlng: str) -> AddressDetails:
    """Get a textual address for a specific location."""
    args = {
        'latlng': latlng,
    }
    result = _call_api(GEOCODE_BASE_URL, args)
    logging.info('latlng=%s:\nresult=\n%s', latlng, pprint.pformat(result))

    # The API result has a lot of information.  We want to score the results
    # so we can select the "best" one.  So we use a simple tuple where the
    # first item is the score and second the address.  We seed the answers
    # with our worst score.
    answers: list[tuple[int, str, set[AddressTypeValue]]] = [
        (LOCATION_TYPE_SCORES['UNKNOWN'], 'No known street address', set())
    ]

    # Google really likes their plus codes.  We use them as a fallback.
    type_: str
    address: str
    for type_, address in list(result['plus_code'].items()):
        score: int = LOCATION_TYPE_SCORES['PLUS'] + PLUS_CODE_SCORES[type_]
        answers.append((score, address, set()))

    for entry in result['results']:
        if 'street_address' in entry['types']:
            type_values: set[AddressTypeValue] = set()
            for component in entry['address_components']:
                name = component['long_name']
                for typ in component['types']:
                    type_values.add(AddressTypeValue(typ=typ, val=name))
            score = LOCATION_TYPE_SCORES[entry['geometry']['location_type']]
            answers.append((score, entry['formatted_address'], type_values))

    answers.sort()
    score, address, type_values = answers[0]
    logging.info('%s: %s (score=%s)', latlng, address, score)
    for type_value in sorted(type_values):
        logging.info('%s: %s', type_value.typ, type_value.val)

    return AddressDetails(address=address, type_values=type_values)


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
    url = base_url + '?' + urllib.parse.urlencode(parameters)
    attempts = 0
    success = False
    while not success and attempts < 3:
        attempts += 1
        try:
            with urllib.request.urlopen(url, timeout=30) as response_data:
                resp = response_data.read()
                logging.debug('resp: %s', resp)
                result = json.loads(resp)
        except (ValueError, urllib.error.URLError, http.client.BadStatusLine,
                socket.error) as err:
            result = {'error_message': str(err), 'status': 'NOTOK'}
        success = result['status'] in ('OK', 'ZERO_RESULTS')
        if not success:
            logging.info('sleeping because %(error_message)s', result)
            time.sleep(5.1)

    if result['status'] == 'OK':
        return result

    if result['status'] == 'ZERO_RESULTS':
        print('strange results:')
        pprint.pprint(result)
        return result

    if result['status'] == 'NOTOK':
        raise NetworkError(result)

    if result['status'] == 'OVER_QUERY_LIMIT':
        raise ApiQueryLimitError(result)

    raise Error(result)
