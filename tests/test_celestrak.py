"""Tests for CelesTrak catalog ingest.

Oracle L2: CelesTrak API docs — https://celestrak.org/NORAD/elements/
"""


from satguard.catalog.celestrak import Catalog, parse_3le_text

# Real 3LE data for testing the parser
SAMPLE_3LE = """\
ISS (ZARYA)
1 25544U 98067A   24045.51749023  .00020825  00000+0  37340-3 0  9992
2 25544  51.6416  14.5021 0006703  38.8378  76.2277 15.49560867441079
CSS (TIANHE)
1 48274U 21035A   24045.35876157  .00025320  00000+0  28844-3 0  9993
2 48274  41.4717 193.8536 0005814 296.5862  72.3277 15.62123810161568"""


class TestParse3LE:
    """L1: Parsing multi-object 3LE text."""

    def test_parse_two_objects(self) -> None:
        """# SOURCE: CelesTrak 3LE format — name + line1 + line2 per object."""
        tles = parse_3le_text(SAMPLE_3LE)
        assert len(tles) == 2

    def test_first_object_is_iss(self) -> None:
        tles = parse_3le_text(SAMPLE_3LE)
        assert tles[0].norad_id == 25544
        assert tles[0].name == "ISS (ZARYA)"

    def test_second_object(self) -> None:
        tles = parse_3le_text(SAMPLE_3LE)
        assert tles[1].norad_id == 48274

    def test_empty_text(self) -> None:
        tles = parse_3le_text("")
        assert len(tles) == 0


class TestCatalog:
    """L1: Catalog lookup tests."""

    def test_catalog_length(self) -> None:
        tles = parse_3le_text(SAMPLE_3LE)
        catalog = Catalog(tles)
        assert len(catalog) == 2

    def test_lookup_by_norad(self) -> None:
        tles = parse_3le_text(SAMPLE_3LE)
        catalog = Catalog(tles)
        iss = catalog.get_by_norad(25544)
        assert iss is not None
        assert iss.name == "ISS (ZARYA)"

    def test_lookup_missing(self) -> None:
        tles = parse_3le_text(SAMPLE_3LE)
        catalog = Catalog(tles)
        assert catalog.get_by_norad(99999) is None

    def test_iteration(self) -> None:
        tles = parse_3le_text(SAMPLE_3LE)
        catalog = Catalog(tles)
        ids = [t.norad_id for t in catalog]
        assert 25544 in ids
        assert 48274 in ids
