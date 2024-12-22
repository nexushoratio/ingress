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
DIRECTIONS_BASE_URL = os.getenv(
    'GMAPS_DIRECTIONS_URL',
    default='https://maps.googleapis.com/maps/api/directions/json'
)
GEOCODE_BASE_URL = os.getenv(
    'GMAPS_GEOCODE_URL',
    default='https://maps.googleapis.com/maps/api/geocode/json'
)

LOCATION_TYPE_SCORES = {
    'ROOFTOP': 0,
    'RANGE_INTERPOLATED': 1,
    'GEOMETRIC_CENTER': 2,
    'APPROXIMATE': 3,
    'PLUS_COMPOUND_CODE': 90,
    'PLUS_GLOBAL_CODE': 91,
    'UNKNOWN': 99,
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


@dataclasses.dataclass(kw_only=True, order=True, frozen=True)
class AddressResult:
    """Address result from the Maps API."""
    location_type: str = dataclasses.field(compare=False)
    score: int = dataclasses.field(init=False)
    pos: int = dataclasses.field(default=0, compare=False)
    address: str
    type_values: set[AddressTypeValue]

    def __post_init__(self):
        # Magic sauce
        object.__setattr__(
            self, 'score', LOCATION_TYPE_SCORES[self.location_type] + self.pos
            - len(self.type_values)
        )


@attr.s
class Directions:  # pylint: disable=missing-class-docstring,too-few-public-methods
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
    # using AddressResult, then select the "best" one.  We seed the answers
    # with our worst score.
    answers = [
        AddressResult(
            address='No known street address',
            type_values=set(),
            location_type='UNKNOWN'
        )
    ]

    # Google really likes their plus codes.  We use them as a fallback.
    type_: str
    address: str
    for type_, address in list(result['plus_code'].items()):
        location_type = '_'.join(('PLUS', type_.upper()))
        answers.append(
            AddressResult(
                address=address,
                type_values=set(),
                location_type=location_type
            )
        )

    for pos, entry in enumerate(result['results']):
        location_type = entry['geometry']['location_type']
        type_values: set[AddressTypeValue] = set()
        for component in entry['address_components']:
            name = component['long_name']
            for typ in component['types']:
                type_values.add(AddressTypeValue(typ=typ, val=name))
        answers.append(
            AddressResult(
                pos=pos,
                address=entry['formatted_address'],
                type_values=type_values,
                location_type=location_type
            )
        )

    answer = _select_result(answers)

    logging.info('\n%s', pprint.pformat(answers))
    for type_value in sorted(answer.type_values):
        logging.info('%s: %s', type_value.typ, type_value.val)

    return AddressDetails(
        address=answer.address, type_values=answer.type_values
    )


def _select_result(results: list[AddressResult]) -> AddressResult:
    """Look through the results for the "best" one."""

    results.sort()
    result0 = results[0]
    # It has been noticed that some results will include one type or another,
    # but not both.  Supplement the selected result with no more than one type
    # might not be present.
    for result in results[1:]:
        for type_value in result.type_values:
            known_types = set(x.typ for x in result0.type_values)
            if type_value.typ not in known_types:
                logging.info('supplementing result with: %s', type_value)
                result0.type_values.add(type_value)
    return result0


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
