'''
Вспомогательный скрипт для сборки odt из распакованного вида.

:Author: В. М. Гореликов <vmgorelikov@edu.hse.ru>
'''

from logging import info
from os import walk
from os.path import dirname, realpath, join, relpath
from time import time
from random import randint
from zipfile import ZipFile, ZIP_DEFLATED


def generate_filename() -> str:
    return f'{int(time())}_{randint(10**6, 10**7-1)}.odt'


script_directory = dirname(realpath(__file__))
uncompressed_dir_name = 'uncompressed_odt'
uncompressed_dir_path = join(script_directory, uncompressed_dir_name)

assembled_odt = ZipFile(
    join(script_directory, generate_filename()), 'w',
    compression=ZIP_DEFLATED, compresslevel=9
)

for root, dirs, files in walk(uncompressed_dir_path):
    for file in files:
        file_path = join(root, file)
        assembled_odt.write(file_path,
                            relpath(file_path,
                                    start=uncompressed_dir_path))

info('OK')
