"""Focused tests for privacy-preserving EXIF helpers."""

from find_api.utils.exif import extract_gps_coordinates


class _Exif(dict):
    def __init__(self, gps):
        super().__init__({0x8825: 1})
        self._gps = gps

    def get_ifd(self, tag):
        assert tag == 0x8825
        return self._gps


class _Image:
    def __init__(self, gps):
        self._exif = _Exif(gps)

    def getexif(self):
        return self._exif


def test_extract_gps_coordinates_converts_dms_and_direction():
    image = _Image(
        {
            1: "N",
            2: (22, 34, 21.36),
            3: "E",
            4: (88, 21, 50.04),
        }
    )

    assert extract_gps_coordinates(image) == (22.5726, 88.3639)


def test_extract_gps_coordinates_applies_south_and_west_signs():
    image = _Image(
        {
            1: "S",
            2: (33, 52, 7.68),
            3: "W",
            4: (151, 12, 33.48),
        }
    )

    assert extract_gps_coordinates(image) == (-33.8688, -151.2093)


def test_extract_gps_coordinates_rejects_partial_coordinates():
    image = _Image({1: "N", 2: (22, 34, 21.36)})

    assert extract_gps_coordinates(image) is None


def test_extract_gps_coordinates_rejects_out_of_range_values():
    image = _Image(
        {
            1: "N",
            2: (95, 0, 0),
            3: "E",
            4: (88, 21, 50.04),
        }
    )

    assert extract_gps_coordinates(image) is None


def test_extract_gps_coordinates_tolerates_malformed_exif():
    image = _Image({1: "N", 2: "not-a-dms-tuple", 3: "E", 4: (1, 2, 3)})

    assert extract_gps_coordinates(image) is None
