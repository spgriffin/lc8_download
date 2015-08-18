# -*- coding: utf-8 -*-
from __future__ import print_function
import requests
from homura import download as fetch

from os.path import join, expanduser, exists, getsize
from os import makedirs

DOWNLOAD_DIR = join(expanduser('~'), 'landsat')

class SceneInfo():
    """Extract informations about scene from sceneName"""
    def __init__(self, sceneName):
        self.name = sceneName
        self.validate_name()
        self.path = sceneName[3:6]
        self.row = sceneName[6:9]
        self.prefix = sceneName[0:3]

    def validate_name(self):
        if len(self.name) < 21:
            raise WrongSceneNameError(self.name)

    def __repr__(self):
        return "Scene :: %s" % self.name


class DownloaderBase:
    """ Base class for classes used to download landsat scene by whatever storage"""

    def __init__(self, sceneInfo):
        if not isinstance(sceneInfo, SceneInfo):
            raise TypeError('sceneInfo must be instance of SceneInfo')
        self.sceneInfo = sceneInfo

    def fetch(self, url, path, filename):
        """Verify if the file is already downloaded and complete. If they don't
        exists or if are not complete,LGN00 use homura download function to fetch
        files. Return a list with the path of the downloaded file and the size
        of the remote file.
        """
        remote_file_size = self.get_remote_file_size(url)

        if exists(join(path, filename)):
            size = getsize(join(path, filename))
            if size == remote_file_size:
                print('%s already exists on your system' % filename)
                return [join(path, filename), size]

        print('Downloading: %s' % filename)
        fetch(url, path)
        print('stored at %s' % path)
        return [join(path, filename), remote_file_size]

    def remote_file_exists(self, url):
        """ Check whether the remote file exists on Storage"""
        return requests.head(url).status_code == 200

    def get_remote_file_size(self, url):
        """ Gets the filesize of a remote file """
        headers = requests.head(url).headers
        return int(headers['content-length'])


class GoogleDownloader(DownloaderBase):
    """Can download scene files from Google Storage"""
    __satellitesMap = {
        'LT5' : 'L5',
        'LE7' : 'L7',
        'LC8' : 'L8'
    }
    __url = 'http://storage.googleapis.com/earthengine-public/landsat/'
    __remote_file_ext = '.tar.bz'

    def __init__ (self, sceneInfo):
        super(GoogleDownloader, self).__init__(sceneInfo)
        self.validate_sceneInfo()
        self.satellite = self.__satellitesMap[sceneInfo.prefix]
        self.remote_file_url = join(
            self.__url,
            self.satellite,
            sceneInfo.path,
            sceneInfo.row,
            sceneInfo.name + self.__remote_file_ext
        )

        if not self.remote_file_exists():
            raise RemoteFileDoesntExist('%s is not available on Google Storage'
                % self.sceneInfo.name)

        print(self.remote_file_url)

    def validate_sceneInfo(self):
        """ Check the scene name and whether remote file exists.
        Raises WrongSceneNameError whether the scene name is wrong
        """
        if self.sceneInfo.prefix not in self.__satellitesMap:
            raise WrongSceneNameError('Google Downloader: Prefix of %s (%s) is invalid'
                % (self.sceneInfo.name, self.sceneInfo.prefix))

    def remote_file_exists(self):
        """ Verify if remote file exists.
        Returns True whether it exists and Fals cause it does not exists
        """
        return super(GoogleDownloader, self).remote_file_exists(self.remote_file_url)

    def download(self, bands, download_dir=None, metadata=False):
        """Download remote tar.gz file with bands from scene specified on sceneInfo"""

        if download_dir is None:
            download_dir = DOWNLOAD_DIR

        dest_dir = check_create_folder(join(download_dir, self.sceneInfo.name))
        filename = "%s.%s" % (self.sceneInfo.name, self.__remote_file_ext)
        downloaded = self.fetch(self.remote_file_url, download_dir, filename)
        return [downloaded]

    def __repr__(self):
        return "Google Downloader (%s)" % self.sceneInfo


class AmazonS3Downloader(DownloaderBase):
    """Can download scene files from Amazon S3 Storage"""
    __url = 'http://landsat-pds.s3.amazonaws.com/L8/'
    __prefixesValid = ('LC8', 'LO8')
    __remote_file_ext = 'TIF'

    def __init__(self, sceneInfo):
        super(AmazonS3Downloader, self).__init__(sceneInfo)

        self.validate_sceneInfo()

        self.base_url = join(
            self.__url,
            sceneInfo.path,
            sceneInfo.row,
            sceneInfo.name)

        if not self.remote_file_exists():
            raise RemoteFileDoesntExist('%s is not available on Amazon S3 Storage'
                % self.sceneInfo.name)

    def validate_sceneInfo(self):
        ''' Check whether sceneInfo is valid to download on Amazon S3 Storage '''
        if self.sceneInfo.prefix not in self.__prefixesValid:
            raise WrongSceneNameError('Amazon S3: Prefix of %s (%s) is invalid'
                % (self.sceneInfo.name, self.sceneInfo.prefix))

    def remote_file_exists(self):
        '''Verify whether the file (scene) exists on Amazon S3 Storage'''
        url = join(self.base_url, 'index.html')
        return super(AmazonS3Downloader, self).remote_file_exists(url)

    def download(self, bands, download_dir=None, metadata=False):
        """ """
        self.validate_bands(bands)
        if download_dir is None:
            download_dir = DOWNLOAD_DIR

        dest_dir = check_create_folder(join(download_dir, self.sceneInfo.name))
        downloaded = []

        for band in bands:
            if band == 'BQA':
                filename = '%s_%s.%s' % (self.sceneInfo.name, band, self.__remote_file_ext)
            else:
                filename = '%s_B%s.%s' % (self.sceneInfo.name, band, self.__remote_file_ext)

            band_url = join(self.base_url, filename)
            downloaded.append(self.fetch(band_url, dest_dir, filename))

        if metadata:
            filename = '%s_MTL.txt' % (self.sceneInfo.name)
            url = join(self.base_url, filename)
            self.fetch(url, dest_dir, filename)
        return downloaded

    def validate_bands(self, bands):
        """Validate bands parameter."""
        if not isinstance(bands, list):
            raise TypeError('Parameter bands must be a "list"')
        valid_bands = list(range(1, 12)) + ['BQA']
        for band in bands:
            if band not in valid_bands:
                raise InvalidBandError('%s is not a valid band' % band)

    def __repr__(self):
        return "Downloader Amazon S3 (%s)" % self.sceneInfo


class Downloader(object):
    """Download Landsat 8 imagery from Amazon servers."""

    def __init__(self, scene, downloaders=None):
        self.downloader = None
        self.sceneInfo = SceneInfo(scene)
        errors = []

        if downloaders is None:
            downloaders = [AmazonS3Downloader, GoogleDownloader]

        for DownloaderClass in downloaders:
            try:
                print("Trying instantiate by %s" % DownloaderClass)
                self.downloader = DownloaderClass(self.sceneInfo)
                break;
            except (WrongSceneNameError, RemoteFileDoesntExist) as error:
                errors.append(error)
                print("%s couldn't be instantiated: (%s)" % (DownloaderClass, error))
        print(self.downloader)
        if self.downloader is None:
            raise DownloaderErrors(errors)

    def download(self, *args, **kwargs):
        print("Downloading by %s" % self.downloader)
        return self.downloader.download(*args, **kwargs)


class WrongSceneNameError(Exception):
    pass


class RemoteFileDoesntExist(Exception):
    pass


class InvalidBandError(Exception):
    pass


class DownloaderErrors(Exception):

    def __init__(self, errors, *args, **kwargs):
        super(DownloaderErrors, self).__init__(*args, **kwargs)
        self.errors = errors


def check_create_folder(folder_path):
    """Check whether a folder exists, if not the folder is created.
    Always return folder_path.
    """
    if not exists(folder_path):
        makedirs(folder_path)

    return folder_path
