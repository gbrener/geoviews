import param
import numpy as np
from cartopy import crs as ccrs
from cartopy.feature import Feature as cFeature
from cartopy.io.img_tiles import GoogleTiles as cGoogleTiles
from cartopy.io.shapereader import Reader
from holoviews.core import Element2D, Dimension, Dataset as HvDataset, NdOverlay
from holoviews.core.util import basestring, pd, max_extents, dimension_range
from holoviews.element import (Text as HvText, Path as HvPath,
                               Polygons as HvPolygons, Image as HvImage,
                               RGB as HvRGB, Contours as HvContours)

from shapely.geometry.base import BaseGeometry
from shapely.geometry import (MultiLineString, LineString,
                              MultiPolygon, Polygon)

try:
    from iris.cube import Cube
except ImportError:
    Cube = None

try:
    from bokeh.models import WMTSTileSource
except:
    WMTSTileSource = None

try:
    from owslib.wmts import WebMapTileService
except:
    WebMapTileService = None

from ..data.geopandas import GeoPandasInterface
from ..util import path_to_geom, polygon_to_geom

geographic_types = (cGoogleTiles, cFeature, BaseGeometry)

def is_geographic(element, kdims=None):
    """
    Utility to determine whether the supplied element optionally
    a subset of its key dimensions represent a geographic coordinate
    system.
    """
    if isinstance(element, NdOverlay):
        element = element.last

    if kdims:
        kdims = [element.get_dimension(d) for d in kdims]
    else:
        kdims = element.kdims

    if len(kdims) != 2:
        return False
    if isinstance(element.data, geographic_types) or isinstance(element, (WMTS, Feature)):
        return True
    elif isinstance(element, _Element):
        return kdims == element.kdims and element.crs
    else:
        return False


class _Element(Element2D):
    """
    Baseclass for Element2D types with associated cartopy
    coordinate reference system.
    """

    _abstract = True

    crs = param.ClassSelector(default=ccrs.PlateCarree(), class_=ccrs.CRS, doc="""
        Cartopy coordinate-reference-system specifying the
        coordinate system of the data. Inferred automatically
        when _Element wraps cartopy Feature object.""")

    kdims = param.List(default=[Dimension('Longitude'), Dimension('Latitude')])

    def __init__(self, data, **kwargs):
        crs = None
        crs_data = data.data if isinstance(data, HvDataset) else data
        if Cube and isinstance(crs_data, Cube):
            coord_sys = crs_data.coord_system()
            if hasattr(coord_sys, 'as_cartopy_projection'):
                crs = coord_sys.as_cartopy_projection()
        elif isinstance(crs_data, (cFeature, cGoogleTiles)):
            crs = crs_data.crs

        supplied_crs = kwargs.get('crs', None)
        if supplied_crs and crs and crs != supplied_crs:
            raise ValueError('Supplied coordinate reference '
                             'system must match crs of the data.')
        elif crs:
            kwargs['crs'] = crs
        super(_Element, self).__init__(data, **kwargs)


    def clone(self, data=None, shared_data=True, new_type=None,
              *args, **overrides):
        if 'crs' not in overrides and (not new_type or isinstance(new_type, _Element)):
            overrides['crs'] = self.crs
        return super(_Element, self).clone(data, shared_data, new_type,
                                           *args, **overrides)


class _GeoFeature(_Element):
    """
    Baseclass for geographic types without their own data.
    """

    _auxiliary_component = True

    def dimension_values(self, dim):
        """
        _GeoFeature types do not contain actual data.
        """
        return []


class Feature(_GeoFeature):
    """
    A Feature represents a geographical feature
    specified as a cartopy Feature type.
    """

    group = param.String(default='Feature')

    def __init__(self, data, **params):
        if not isinstance(data, cFeature):
            raise TypeError('%s data has to be an cartopy Feature type'
                            % type(data).__name__)
        super(Feature, self).__init__(data, **params)

    def range(self, dim, data_range=True):
        didx = self.get_dimension_index(dim)
        if didx in [0, 1] and data_range:
            dim = self.get_dimension(dim)
            l, b, r, t = max_extents([geom.bounds for geom in self.data.geometries()])
            lower, upper = (b, t) if didx else (l, r)
            return dimension_range(lower, upper, dim)
        return super(Feature, self).range(dim, data_range)


class WMTS(_GeoFeature):
    """
    The WMTS Element represents a Web Map Tile Service
    specified as a tuple of the API URL and
    """

    group = param.String(default='WMTS')

    layer = param.String(doc="The layer on the tile service")

    def __init__(self, data, **params):
        if isinstance(data, tuple):
            data = data
        else:
            data = (data,)

        for d in data:
            if WMTSTileSource and isinstance(d, WMTSTileSource):
                if 'crs' not in params:
                    params['crs'] = ccrs.GOOGLE_MERCATOR
            elif WebMapTileService and isinstance(d, WebMapTileService):
                if 'crs' not in params and not self.crs:
                    raise Exception('Must supply coordinate reference '
                                    'system with cartopy WMTS URL.')
            elif not isinstance(d, basestring):
                raise TypeError('%s data has to be a tile service URL'
                                % type(d).__name__)
        super(WMTS, self).__init__(data, **params)


class Tiles(_GeoFeature):
    """
    Tiles represents an image tile source to dynamically
    load data from depending on the zoom level.
    """

    group = param.String(default='Tiles')

    def __init__(self, data, **params):
        if not isinstance(data, cGoogleTiles):
            raise TypeError('%s data has to be a cartopy GoogleTiles type'
                            % type(data).__name__)
        super(Tiles, self).__init__(data, **params)



class Dataset(_Element, HvDataset):
    """
    Coordinate system aware version of a HoloViews dataset.
    """


class Points(Dataset):
    """
    Points represent a collection of points with
    an associated cartopy coordinate-reference system.
    """

    group = param.String(default='Points')


class LineContours(_Element, HvImage):
    """
    Contours represents a 2D array of some quantity with
    some associated coordinates, which may be discretized
    into one or more line contours.
    """

    vdims = param.List(default=[Dimension('z')], bounds=(1, 1))

    group = param.String(default='LineContours')


class FilledContours(LineContours):
    """
    Contours represents a 2D array of some quantity with
    some associated coordinates, which may be discretized
    into one or more filled contours.
    """

    group = param.String(default='FilledContours')


class Image(_Element, HvImage):
    """
    Image represents a 2D array of some quantity with
    some associated coordinates.
    """

    vdims = param.List(default=[Dimension('z')], bounds=(1, 1))

    group = param.String(default='Image')


class RGB(_Element, HvRGB):
    """
    An RGB element is a Image containing channel data for the the
    red, green, blue and (optionally) the alpha channels. The values
    of each channel must be in the range 0.0 to 1.0.

    In input array may have a shape of NxMx4 or NxMx3. In the latter
    case, the defined alpha dimension parameter is appended to the
    list of value dimensions.
    """

    group = param.String(default='RGB', constant=True)

    vdims = param.List(
        default=[Dimension('R', range=(0,1)), Dimension('G',range=(0,1)),
                 Dimension('B', range=(0,1))], bounds=(3, 4), doc="""
        The dimension description of the data held in the matrix.

        If an alpha channel is supplied, the defined alpha_dimension
        is automatically appended to this list.""")


class Text(HvText, _Element):
    """
    An annotation containing some text at an x, y coordinate
    along with a coordinate reference system.
    """


class Path(_Element, HvPath):
    """
    The Path Element contains a list of Paths stored as Nx2 numpy
    arrays along with a coordinate reference system.
    """

    def geom(self):
        """
        Returns Path as a shapely geometry.
        """
        return path_to_geom(self)


class Contours(_Element, HvContours):
    """
    Contours is a Path Element type that may contain any number of
    closed paths with an associated value and a coordinate reference
    system.
    """

    def geom(self):
        """
        Returns Path as a shapely geometry.
        """
        return path_to_geom(self)


class Polygons(_Element, HvPolygons):
    """
    Polygons is a Path Element type that may contain any number of
    closed paths with an associated value and a coordinate reference
    system.
    """

    def geom(self):
        """
        Returns Path as a shapely geometry.
        """
        return polygon_to_geom(self)


class Shape(_Element):
    """
    Shape wraps any shapely geometry type.
    """

    group = param.String(default='Shape')

    level = param.Number(default=None, doc="""
        Optional level associated with the set of Contours.""")

    vdims = param.List(default=[Dimension('Level')], doc="""
        Contours optionally accept a value dimension, corresponding
        to the supplied values.""", bounds=(1,1))

    def __init__(self, data, **params):
        if not isinstance(data, BaseGeometry):
            raise TypeError('%s data has to be a shapely geometry type.'
                            % type(data).__name__)
        super(Shape, self).__init__(data, **params)


    @classmethod
    def from_shapefile(cls, shapefile, *args, **kwargs):
        """
        Loads a shapefile from disk and optionally merges
        it with a dataset. See ``from_records`` for full
        signature.
        """
        reader = Reader(shapefile)
        return cls.from_records(reader.records(), *args, **kwargs)


    @classmethod
    def from_records(cls, records, dataset=None, on=None,
                     value=None, index=[], drop_missing=False, **kwargs):
        """
        Load data from a collection of
        ``cartopy.io.shapereader.Record`` objects and optionally merge
        it with a dataset to assign values to each polygon and form a
        chloropleth. Supplying just records will return an NdOverlay
        of Shape Elements with a numeric index. If a dataset is
        supplied, a mapping between the attribute names in the records
        and the dimension names in the dataset must be supplied. The
        values assigned to each shape file can then be drawn from the
        dataset by supplying a ``value`` and keys the Shapes are
        indexed by specifying one or index dimensions.

        * records - An iterator of cartopy.io.shapereader.Record
                    objects.
        * dataset - Any HoloViews Dataset type.
        * on      - A mapping between the attribute names in
                    the records and the dimensions in the dataset.
        * value   - The value dimension in the dataset the
                    values will be drawn from.
        * index   - One or more dimensions in the dataset
                    the Shapes will be indexed by.
        * drop_missing - Whether to drop shapes which are missing from
                         the provided dataset.

        Returns an NdOverlay of Shapes.
        """
        if dataset is not None and not on:
            raise ValueError('To merge dataset with shapes mapping '
                             'must define attribute(s) to merge on.')

        if pd and isinstance(dataset, pd.DataFrame):
            dataset = Dataset(dataset)

        if not isinstance(on, (dict, list)):
            on = [on]
        if on and not isinstance(on, dict):
            on = {o: o for o in on}
        if not isinstance(index, list):
            index = [index]

        kdims = []
        for ind in (index if index else ['Index']):
            if dataset and dataset.get_dimension(ind):
                dim = dataset.get_dimension(ind)
            else:
                dim = Dimension(ind)
            kdims.append(dim)

        ddims = []
        if dataset:
            vdim = dataset.get_dimension(value)
            kwargs['vdims'] = [vdim]
            if not vdim:
                raise ValueError('Value dimension not found '
                                 'in dataset: {}'.format(vdim))
            ddims = dataset.dimensions()

        data = []
        notfound = False
        for i, rec in enumerate(records):
            if dataset:
                selection = {dim: rec.attributes.get(attr, None)
                             for attr, dim in on.items()}
                row = dataset.select(**selection)
                if len(row):
                    value = row[vdim.name][0]
                elif drop_missing:
                    continue
                else:
                    value = np.NaN
                kwargs['level'] = value
            if index:
                key = []
                for kdim in kdims:
                    if kdim in ddims and len(row):
                        k = row[kdim.name][0]
                    elif kdim.name in rec.attributes:
                        k = rec.attributes[kdim.name]
                    else:
                        k = None
                        notfound = True
                    key.append(k)
                key = tuple(key)
            else:
                key = (i,)
            data.append((key, Shape(rec.geometry, **kwargs)))
        if notfound:
            kdims = ['Index']+kdims
            data = [((i,)+subk, v) for i, (subk, v) in enumerate(data)]
        return NdOverlay(data, kdims=kdims)


    def dimension_values(self, dimension):
        """
        Shapes do not support convert to array values.
        """
        dim = self.get_dimension(dimension)
        if dim in self.vdims:
            return [self.level]
        else:
            return []


    def range(self, dim, data_range=True):
        dim = self.get_dimension(dim)
        if dim.range != (None, None):
            return dim.range

        idx = self.get_dimension_index(dim)
        if idx == 2 and data_range:
            return self.level, self.level
        if idx in [0, 1] and data_range:
            l, b, r, t = self.data.bounds
            lower, upper = (b, t) if idx else (l, r)
            return dimension_range(lower, upper, dim)
        else:
            return super(Shape, self).range(dim, data_range)


    def geom(self):
        """
        Returns Shape as a shapely geometry
        """
        return self.data


    def __len__(self):
        return len(self.data)
