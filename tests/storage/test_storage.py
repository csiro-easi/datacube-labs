from __future__ import absolute_import, division, print_function

from contextlib import contextmanager

import mock
import netCDF4
import numpy as np
import pytest
import rasterio.warp
from affine import Affine, identity

import datacube
from datacube.drivers.datasource import DataSource
from datacube.model import Dataset, DatasetType, MetadataType
from datacube.model import Variable
from datacube.storage.storage import OverrideBandDataSource, RasterFileDataSource, create_netcdf_storage_unit
from datacube.storage.storage import write_dataset_to_netcdf, reproject_and_fuse, read_from_source, Resampling, \
    RasterDatasetDataSource
from datacube.utils import geometry
from datacube.utils.geometry import GeoBox, CRS


def test_write_dataset_to_netcdf(tmpnetcdf_filename, odc_style_xr_dataset):
    write_dataset_to_netcdf(odc_style_xr_dataset, tmpnetcdf_filename, global_attributes={'foo': 'bar'},
                            variable_params={'B10': {'attrs': {'abc': 'xyz'}}})

    with netCDF4.Dataset(tmpnetcdf_filename) as nco:
        nco.set_auto_mask(False)
        assert 'B10' in nco.variables
        var = nco.variables['B10']
        assert (var[:] == odc_style_xr_dataset['B10'].values).all()

        assert 'foo' in nco.ncattrs()
        assert nco.getncattr('foo') == 'bar'

        assert 'abc' in var.ncattrs()
        assert var.getncattr('abc') == 'xyz'


# def test_netcdf_source(tmpnetcdf_filename):
#     affine = Affine.scale(0.1, 0.1) * Affine.translation(20, 30)
#     geobox = geometry.GeoBox(110, 100, affine, geometry.CRS(GEO_PROJ))
#     dataset = xarray.Dataset(attrs={'extent': geobox.extent, 'crs': geobox.crs})
#     for name, coord in geobox.coordinates.items():
#         dataset[name] = (name, coord.values, {'units': coord.units, 'crs': geobox.crs})
#
#     dataset['B10'] = (geobox.dimensions,
#                       np.arange(11000, dtype='int16').reshape(geobox.shape),
#                       {'nodata': 0, 'units': '1', 'crs': geobox.crs})
#
#     write_dataset_to_netcdf(dataset, tmpnetcdf_filename, global_attributes={'foo': 'bar'},
#                             variable_params={'B10': {'attrs': {'abc': 'xyz'}}})
#
#     with netCDF4.Dataset(tmpnetcdf_filename) as nco:
#         nco.set_auto_mask(False)
#         source = NetCDFDataSource(nco, 'B10')
#         assert source.crs == geobox.crs
#         assert source.transform.almost_equals(affine)
#         assert (source.read() == dataset['B10']).all()
#
#         dest = np.empty((60, 50))
#         source.reproject(dest, affine, geobox.crs, 0, Resampling.nearest)
#         assert (dest == dataset['B10'][:60, :50]).all()
#
#         source.reproject(dest, affine * Affine.translation(10, 10), geobox.crs, 0, Resampling.nearest)
#         assert (dest == dataset['B10'][10:70, 10:60]).all()
#
#         source.reproject(dest, affine * Affine.translation(-10, -10), geobox.crs, 0, Resampling.nearest)
#         assert (dest[10:, 10:] == dataset['B10'][:50, :40]).all()
#
#         dest = np.empty((200, 200))
#         source.reproject(dest, affine, geobox.crs, 0, Resampling.nearest)
#         assert (dest[:100, :110] == dataset['B10']).all()
#
#         source.reproject(dest, affine * Affine.translation(10, 10), geobox.crs, 0, Resampling.nearest)
#         assert (dest[:90, :100] == dataset['B10'][10:, 10:]).all()
#
#         source.reproject(dest, affine * Affine.translation(-10, -10), geobox.crs, 0, Resampling.nearest)
#         assert (dest[10:110, 10:120] == dataset['B10']).all()
#
#         source.reproject(dest, affine * Affine.scale(2, 2), geobox.crs, 0, Resampling.nearest)
#         assert (dest[:50, :55] == dataset['B10'][1::2, 1::2]).all()
#
#         source.reproject(dest, affine * Affine.scale(2, 2) * Affine.translation(10, 10),
#                          geobox.crs, 0, Resampling.nearest)
#         assert (dest[:40, :45] == dataset['B10'][21::2, 21::2]).all()
#
#         source.reproject(dest, affine * Affine.scale(2, 2) * Affine.translation(-10, -10),
#                          geobox.crs, 0, Resampling.nearest)
#         assert (dest[10:60, 10:65] == dataset['B10'][1::2, 1::2]).all()


def test_first_source_is_priority_in_reproject_and_fuse():
    crs = geometry.CRS('EPSG:4326')
    shape = (2, 2)
    no_data = -1

    source1 = FakeDatasetSource([[1, 1], [1, 1]], crs=crs, shape=shape)
    source2 = FakeDatasetSource([[2, 2], [2, 2]], crs=crs, shape=shape)
    sources = [source1, source2]

    output_data = np.full(shape, fill_value=no_data, dtype='int16')
    reproject_and_fuse(sources, output_data, dst_transform=identity, dst_projection=crs, dst_nodata=no_data)

    assert (output_data == 1).all()


def test_second_source_used_when_first_is_empty():
    crs = geometry.CRS('EPSG:4326')
    shape = (2, 2)
    no_data = -1

    source1 = FakeDatasetSource([[-1, -1], [-1, -1]], crs=crs, shape=shape)
    source2 = FakeDatasetSource([[2, 2], [2, 2]], crs=crs, shape=shape)
    sources = [source1, source2]

    output_data = np.full(shape, fill_value=no_data, dtype='int16')
    reproject_and_fuse(sources, output_data, dst_transform=identity, dst_projection=crs, dst_nodata=no_data)

    assert (output_data == 2).all()


def test_mixed_result_when_first_source_partially_empty():
    crs = geometry.CRS('EPSG:4326')
    shape = (2, 2)
    no_data = -1

    source1 = FakeDatasetSource([[1, 1], [no_data, no_data]], crs=crs)
    source2 = FakeDatasetSource([[2, 2], [2, 2]], crs=crs)
    sources = [source1, source2]

    output_data = np.full(shape, fill_value=no_data, dtype='int16')
    reproject_and_fuse(sources, output_data, dst_transform=identity, dst_projection=crs, dst_nodata=no_data)

    assert (output_data == [[1, 1], [2, 2]]).all()


def test_mixed_result_when_first_source_partially_empty_with_nan_nodata():
    crs = geometry.CRS('EPSG:4326')
    shape = (2, 2)
    no_data = np.nan

    source1 = FakeDatasetSource([[1, 1], [no_data, no_data]], crs=crs)
    source2 = FakeDatasetSource([[2, 2], [2, 2]], crs=crs)
    sources = [source1, source2]

    output_data = np.full(shape, fill_value=no_data, dtype='float64')
    reproject_and_fuse(sources, output_data, dst_transform=identity, dst_projection=crs, dst_nodata=no_data)

    assert (output_data == [[1, 1], [2, 2]]).all()


class FakeBandDataSource(object):
    def __init__(self, value, nodata, shape=(2, 2), *args, **kwargs):
        self.value = value
        self.crs = geometry.CRS('EPSG:4326')
        self.transform = Affine.identity()
        self.dtype = np.int16 if not np.isnan(nodata) else np.float64
        self.shape = shape
        self.nodata = nodata

    def read(self, window=None, out_shape=None):
        """Read data in the native format, returning a numpy array
        """
        return np.array(self.value)

    def reproject(self, dest, dst_transform, dst_crs, dst_nodata, resampling, **kwargs):
        return np.array(self.value)


class FakeDatasetSource(DataSource):
    def __init__(self, value, bandnumber=1, nodata=-999, shape=(2, 2), crs=None, transform=None,
                 band_source_class=FakeBandDataSource):
        super(FakeDatasetSource, self).__init__()
        self.value = value
        self.bandnumber = bandnumber
        self.crs = crs
        self.transform = transform
        self.band_source_class = band_source_class
        self.shape = shape
        self.nodata = nodata

    def get_bandnumber(self, src):
        return self.bandnumber

    def get_transform(self, shape):
        if self.transform is None:
            raise RuntimeError('No transform in the data and no fallback')
        return self.transform

    def get_crs(self):
        if self.crs is None:
            raise RuntimeError('No CRS in the data and no fallback')
        return self.crs

    @contextmanager
    def open(self):
        """Context manager which returns a :class:`BandDataSource`"""
        yield self.band_source_class(value=self.value, nodata=self.nodata, shape=self.shape)


class BrokenBandDataSource(FakeBandDataSource):
    def read(self, window=None, out_shape=None):
        raise OSError('Read or write failed')


def test_read_from_broken_source():
    crs = geometry.CRS('EPSG:4326')
    shape = (2, 2)
    no_data = -1

    source1 = FakeDatasetSource(value=[[1, 1], [no_data, no_data]], crs=crs, band_source_class=BrokenBandDataSource)
    source2 = FakeDatasetSource(value=[[2, 2], [2, 2]], crs=crs)
    sources = [source1, source2]

    output_data = np.full(shape, fill_value=no_data, dtype='int16')

    # Check exception is raised
    with pytest.raises(OSError):
        reproject_and_fuse(sources, output_data, dst_transform=identity,
                           dst_projection=crs, dst_nodata=no_data)

    # Check can ignore errors
    reproject_and_fuse(sources, output_data, dst_transform=identity,
                       dst_projection=crs, dst_nodata=no_data, skip_broken_datasets=True)

    assert (output_data == [[2, 2], [2, 2]]).all()


def _create_broken_netcdf(tmpdir):
    import os
    output_path = str(tmpdir / 'broken_netcdf_file.nc')
    with netCDF4.Dataset('broken_netcdf_file.nc', 'w') as nco:
        nco.createDimension('x', 50)
        nco.createDimension('y', 50)
        nco.createVariable('blank', 'int16', ('y', 'x'))

    with open(output_path, 'rb+') as filehandle:
        filehandle.seek(-3, os.SEEK_END)
        filehandle.truncate()

    with netCDF4.Dataset(output_path) as nco:
        blank = nco.data_vars['blank']


class FakeDataSource(object):
    def __init__(self):
        self.crs = geometry.CRS('EPSG:4326')
        self.transform = Affine(0.25, 0, 100, 0, -0.25, -30)
        self.nodata = -999
        self.shape = (613, 597)

        self.data = np.full(self.shape, self.nodata, dtype='int16')
        self.data[:512, :512] = np.arange(512) + np.arange(512).reshape((512, 1))

    def read(self, window=None, out_shape=None):
        data = self.data
        if window:
            data = self.data[slice(*window[0]), slice(*window[1])]
        if out_shape:
            xidx = ((np.arange(out_shape[1]) + 0.5) * (data.shape[1] / out_shape[1]) - 0.5).round().astype('int')
            yidx = ((np.arange(out_shape[0]) + 0.5) * (data.shape[0] / out_shape[0]) - 0.5).round().astype('int')
            data = data[np.meshgrid(yidx, xidx, indexing='ij')]
        return data

    def reproject(self, dest, dst_transform, dst_crs, dst_nodata, resampling, **kwargs):
        return rasterio.warp.reproject(self.data,
                                       dest,
                                       src_transform=self.transform,
                                       src_crs=str(self.crs),
                                       src_nodata=self.nodata,
                                       dst_transform=dst_transform,
                                       dst_crs=str(dst_crs),
                                       dst_nodata=dst_nodata,
                                       resampling=resampling,
                                       **kwargs)


def assert_same_read_results(source, dst_shape, dst_dtype, dst_transform, dst_nodata, dst_projection, resampling):
    expected = np.empty(dst_shape, dtype=dst_dtype)
    with source.open() as src:
        rasterio.warp.reproject(src.data,
                                expected,
                                src_transform=src.transform,
                                src_crs=str(src.crs),
                                src_nodata=src.nodata,
                                dst_transform=dst_transform,
                                dst_crs=str(dst_projection),
                                dst_nodata=dst_nodata,
                                resampling=resampling)

    result = np.empty(dst_shape, dtype=dst_dtype)
    with datacube.set_options(reproject_threads=1):
        read_from_source(source,
                         result,
                         dst_transform=dst_transform,
                         dst_nodata=dst_nodata,
                         dst_projection=dst_projection,
                         resampling=resampling)

    assert np.isclose(result, expected, atol=0, rtol=0.05, equal_nan=True).all()
    return result


def test_read_from_fake_source():
    data_source = FakeDataSource()

    @contextmanager
    def fake_open():
        yield data_source

    source = mock.Mock()
    source.open = fake_open

    # one-to-one copy
    assert_same_read_results(
        source,
        dst_shape=data_source.shape,
        dst_dtype=data_source.data.dtype,
        dst_transform=data_source.transform,
        dst_nodata=data_source.nodata,
        dst_projection=data_source.crs,
        resampling=Resampling.nearest)

    # change dtype
    assert_same_read_results(
        source,
        dst_shape=data_source.shape,
        dst_dtype='int32',
        dst_transform=data_source.transform,
        dst_nodata=data_source.nodata,
        dst_projection=data_source.crs,
        resampling=Resampling.nearest)

    # change nodata
    assert_same_read_results(
        source,
        dst_shape=data_source.shape,
        dst_dtype='float32',
        dst_transform=data_source.transform,
        dst_nodata=float('nan'),
        dst_projection=data_source.crs,
        resampling=Resampling.nearest)

    # different offsets/sizes
    assert_same_read_results(
        source,
        dst_shape=(517, 557),
        dst_dtype='float32',
        dst_transform=data_source.transform * Affine.translation(-200, -200),
        dst_nodata=float('nan'),
        dst_projection=data_source.crs,
        resampling=Resampling.nearest)

    assert_same_read_results(
        source,
        dst_shape=(807, 879),
        dst_dtype='float32',
        dst_transform=data_source.transform * Affine.translation(200, 200),
        dst_nodata=float('nan'),
        dst_projection=data_source.crs,
        resampling=Resampling.nearest)

    assert_same_read_results(
        source,
        dst_shape=(807, 879),
        dst_dtype='float32',
        dst_transform=data_source.transform * Affine.translation(1500, -1500),
        dst_nodata=float('nan'),
        dst_projection=data_source.crs,
        resampling=Resampling.nearest)

    # flip axis
    assert_same_read_results(
        source,
        dst_shape=(517, 557),
        dst_dtype='float32',
        dst_transform=data_source.transform * Affine.translation(0, 512) * Affine.scale(1, -1),
        dst_nodata=float('nan'),
        dst_projection=data_source.crs,
        resampling=Resampling.nearest)

    assert_same_read_results(
        source,
        dst_shape=(517, 557),
        dst_dtype='float32',
        dst_transform=data_source.transform * Affine.translation(512, 0) * Affine.scale(-1, 1),
        dst_nodata=float('nan'),
        dst_projection=data_source.crs,
        resampling=Resampling.nearest)

    # scale
    assert_same_read_results(
        source,
        dst_shape=(250, 500),
        dst_dtype='float32',
        dst_transform=data_source.transform * Affine.scale(2, 4),
        dst_nodata=float('nan'),
        dst_projection=data_source.crs,
        resampling=Resampling.nearest)

    assert_same_read_results(
        source,
        dst_shape=(500, 250),
        dst_dtype='float32',
        dst_transform=data_source.transform * Affine.scale(4, 2),
        dst_nodata=float('nan'),
        dst_projection=data_source.crs,
        resampling=Resampling.cubic)

    assert_same_read_results(
        source,
        dst_shape=(67, 35),
        dst_dtype='float32',
        dst_transform=data_source.transform * Affine.scale(16, 8),
        dst_nodata=float('nan'),
        dst_projection=data_source.crs,
        resampling=Resampling.cubic)

    assert_same_read_results(
        source,
        dst_shape=(35, 67),
        dst_dtype='float32',
        dst_transform=data_source.transform * Affine.translation(27, 35) * Affine.scale(8, 16),
        dst_nodata=float('nan'),
        dst_projection=data_source.crs,
        resampling=Resampling.cubic)

    assert_same_read_results(
        source,
        dst_shape=(35, 67),
        dst_dtype='float32',
        dst_transform=data_source.transform * Affine.translation(-13, -27) * Affine.scale(8, 16),
        dst_nodata=float('nan'),
        dst_projection=data_source.crs,
        resampling=Resampling.cubic)

    # scale + flip
    assert_same_read_results(
        source,
        dst_shape=(35, 67),
        dst_dtype='float32',
        dst_transform=data_source.transform * Affine.translation(15, 512 + 17) * Affine.scale(8, -16),
        dst_nodata=float('nan'),
        dst_projection=data_source.crs,
        resampling=Resampling.cubic)

    assert_same_read_results(
        source,
        dst_shape=(67, 35),
        dst_dtype='float32',
        dst_transform=data_source.transform * Affine.translation(512 - 23, -29) * Affine.scale(-16, 8),
        dst_nodata=float('nan'),
        dst_projection=data_source.crs,
        resampling=Resampling.cubic)

    # TODO: crs change


class TestRasterDataReading(object):
    @pytest.mark.parametrize("dst_nodata", [
        np.nan, float("nan"), -999
    ])
    def xtest_failed_data_read(self, make_sample_geotiff, dst_nodata):
        sample_geotiff_path, geobox, written_data = make_sample_geotiff(dst_nodata)

        src_transform = Affine(25.0, 0.0, 1200000.0,
                               0.0, -25.0, -4200000.0)
        source = RasterFileDataSource(sample_geotiff_path, 1, transform=src_transform)

        dest = np.zeros((20, 100))
        dst_nodata = -999
        dst_projection = geometry.CRS('EPSG:3577')
        dst_resampling = Resampling.nearest

        # Read exactly the hunk of data that we wrote
        dst_transform = Affine(25.0, 0.0, 127327.0,
                               0.0, -25.0, -417232.0)
        read_from_source(source, dest, dst_transform, dst_nodata, dst_projection, dst_resampling)

        assert np.all(written_data == dest)

    @pytest.mark.parametrize("dst_nodata", [
        np.nan, float("nan"), -999
    ])
    def test_read_with_rasterfiledatasource(self, make_sample_geotiff, dst_nodata):
        sample_geotiff_path, geobox, written_data = make_sample_geotiff(dst_nodata)

        source = RasterFileDataSource(str(sample_geotiff_path), 1)

        dest = np.zeros_like(written_data)
        dst_transform = geobox.transform
        dst_projection = geometry.CRS('EPSG:3577')
        dst_resampling = Resampling.nearest

        # Read exactly the hunk of data that we wrote
        read_from_source(source, dest, dst_transform, dst_nodata, dst_projection, dst_resampling)

        assert np.all(written_data == dest)

        # Try reading from partially outside of our area
        xoff = 50
        offset_transform = dst_transform * Affine.translation(xoff, 0)
        dest = np.zeros_like(written_data)

        read_from_source(source, dest, offset_transform, dst_nodata, dst_projection, dst_resampling)
        assert np.all(written_data[:, xoff:] == dest[:, :xoff])

        # Try reading from complete outside of our area, should return nodata
        xoff = 300
        offset_transform = dst_transform * Affine.translation(xoff, 0)
        dest = np.zeros_like(written_data)

        read_from_source(source, dest, offset_transform, dst_nodata, dst_projection, dst_resampling)
        if np.isnan(dst_nodata):
            assert np.all(np.isnan(dest))
        else:
            assert np.all(dst_nodata == dest)

    @pytest.mark.parametrize("dst_transform", [
        Affine(25.0, 0.0, 1273275.0, 0.0, -25.0, -4172325.0),
        Affine(25.0, 0.0, 127327.0, 0.0, -25.0, -417232.0)
    ])
    def test_read_data_from_outside_file_region(self, make_sample_netcdf, dst_transform):
        sample_nc, geobox, written_data = make_sample_netcdf

        source = RasterFileDataSource(sample_nc, 1)

        dest = np.zeros((200, 1000))
        dst_nodata = -999
        dst_projection = geometry.CRS('EPSG:3577')
        dst_resampling = Resampling.nearest

        # Read exactly the hunk of data that we wrote
        read_from_source(source, dest, dst_transform, dst_nodata, dst_projection, dst_resampling)

        assert np.all(dest == -999)

    def test_read_with_custom_crs_and_transform(self, example_gdal_path):
        with rasterio.open(example_gdal_path) as src:
            band = rasterio.band(src, 1)
            crs = geometry.CRS('EPSG:3577')
            nodata = -999
            transform = Affine(25.0, 0.0, 1000000.0,
                               0.0, -25.0, -900000.0)

            # Read all raw data from source file
            band_data_source = OverrideBandDataSource(band, nodata, crs, transform)
            dest1 = band_data_source.read()
            assert dest1.shape

            # Attempt to read with the same transform parameters
            dest2 = np.full(shape=(4000, 4000), fill_value=nodata, dtype=np.float32)
            dst_transform = transform
            dst_crs = crs
            dst_nodata = nodata
            resampling = datacube.storage.storage.RESAMPLING_METHODS['nearest']
            band_data_source.reproject(dest2, dst_transform, dst_crs, dst_nodata, resampling)
            assert (dest1 == dest2).all()

    def test_read_from_file_with_missing_crs(self, no_crs_gdal_path):
        """
        We need to be able to read from data files even when GDAL can't automatically gather all the metdata.

        The :class:`RasterFileDataSource` is able to override the nodata, CRS and transform attributes if necessary.
        """
        crs = geometry.CRS('EPSG:4326')
        nodata = -999
        transform = Affine(0.01, 0.0, 111.975,
                           0.0, 0.01, -9.975)
        data_source = RasterFileDataSource(no_crs_gdal_path, bandnumber=1, nodata=nodata, crs=crs, transform=transform)
        with data_source.open() as src:
            dest1 = src.read()
            assert dest1.shape == (10, 10)


@pytest.fixture
def make_sample_netcdf(tmpdir):
    """Make a test Geospatial NetCDF file, 4000x4000 int16 random data, in a variable named `sample`.
    Return the GDAL access string."""
    sample_nc = str(tmpdir.mkdir('netcdfs').join('sample.nc'))
    geobox = GeoBox(4000, 4000, affine=Affine(25.0, 0.0, 1200000, 0.0, -25.0, -4200000), crs=CRS('EPSG:3577'))

    sample_data = np.random.randint(10000, size=(4000, 4000), dtype=np.int16)

    variables = {'sample': Variable(sample_data.dtype, nodata=-999, dims=geobox.dimensions, units=1)}
    nco = create_netcdf_storage_unit(sample_nc, geobox.crs, geobox.coordinates, variables=variables, variable_params={})

    nco['sample'][:] = sample_data

    nco.close()

    return "NetCDF:%s:sample" % sample_nc, geobox, sample_data


@pytest.fixture
def make_sample_geotiff(tmpdir):
    """ Make a sample geotiff, filled with random data, and twice as tall as it is wide. """
    def internal_make_sample_geotiff(nodata=-999):
        sample_geotiff = str(tmpdir.mkdir('tiffs').join('sample.tif'))

        geobox = GeoBox(100, 200, affine=Affine(25.0, 0.0, 0, 0.0, -25.0, 0), crs=CRS('EPSG:3577'))
        if np.isnan(nodata):
            out_dtype = 'float64'
            sample_data = 10000 * np.random.random_sample(size=geobox.shape)
        else:
            out_dtype = 'int16'
            sample_data = np.random.randint(10000, size=geobox.shape, dtype=out_dtype)
        rio_args = {
            'height': geobox.height,
            'width': geobox.width,
            'count': 1,
            'dtype': out_dtype,
            'crs': 'EPSG:3577',
            'transform': geobox.transform,
            'nodata': nodata
        }
        with rasterio.open(sample_geotiff, 'w', driver='GTiff', **rio_args) as dst:
            dst.write(sample_data, 1)

        return sample_geotiff, geobox, sample_data
    return internal_make_sample_geotiff


_EXAMPLE_METADATA_TYPE = MetadataType(
    {
        'name': 'eo',
        'dataset': dict(
            id=['id'],
            label=['ga_label'],
            creation_time=['creation_dt'],
            measurements=['image', 'bands'],
            sources=['lineage', 'source_datasets'],
            format=['format', 'name'],
        )
    },
    dataset_search_fields={}
)

_EXAMPLE_DATASET_TYPE = DatasetType(
    _EXAMPLE_METADATA_TYPE,
    {
        'name': 'ls5_nbar_scene',
        'description': "Landsat 5 NBAR 25 metre",
        'metadata_type': 'eo',
        'metadata': {},
        'measurements': [
            {'aliases': ['band_2', '2'],
             'dtype': 'int16',
             'name': 'green',
             'nodata': -999,
             'units': '1'}],
    }
)


def test_multiband_support_in_datasetsource(example_gdal_path):
    defn = {
        "id": '12345678123456781234567812345678',
        "format": {"name": "GeoTiff"},
        "image": {
            "bands": {
                'green': {
                    'type': 'reflective',
                    'cell_size': 25.0,
                    'path': example_gdal_path,
                    'label': 'Coastal Aerosol',
                    'number': '1',
                },
            }
        }
    }

    # Without new band attribute, default to band number 1
    d = Dataset(_EXAMPLE_DATASET_TYPE, defn, uris=['file:///tmp'])

    ds = RasterDatasetDataSource(d, measurement_id='green')

    bandnum = ds.get_bandnumber(None)

    assert bandnum == 1

    with ds.open() as foo:
        data = foo.read()
        assert isinstance(data, np.ndarray)

    #############
    # With new 'image.bands.[band].band' attribute
    band_num = 3
    defn['image']['bands']['green']['band'] = band_num
    d = Dataset(_EXAMPLE_DATASET_TYPE, defn, uris=['file:///tmp'])

    ds = RasterDatasetDataSource(d, measurement_id='green')

    assert ds.get_bandnumber(None) == band_num


def test_netcdf_multi_part():
    defn = {
        "id": '12345678123456781234567812345678',
        "format": {"name": "NetCDF CF"},
        "image": {
            "bands": {
                'green': {
                    'type': 'reflective',
                    'cell_size': 25.0,
                    'layer': 'green',
                    'path': '',
                    'label': 'Coastal Aerosol',
                },
            }
        }
    }

    def ds(uri):
        d = Dataset(_EXAMPLE_DATASET_TYPE, defn, uris=[uri])
        return RasterDatasetDataSource(d, measurement_id='green')

    for i in range(3):
        assert ds('file:///tmp.nc#part=%d' % i).get_bandnumber() == (i+1)

    # can't tell without opening file
    assert ds('file:///tmp.nc').get_bandnumber() is None
