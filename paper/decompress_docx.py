'''
Вспомогательный скрипт для распаковки DOCX для более эффективного
контроля версий.

:Author: В. М. Гореликов <vmgorelikov@edu.hse.ru>
'''
from logging import warning, fatal, info
from glob import glob
from os import makedirs, scandir
from os.path import dirname, realpath, join, isabs, isdir, isfile
from sys import argv
from random import randint
from zipfile import ZipFile


def sprinkle_in_code(message_: str, code_length: int = 6)\
        -> tuple[str, str]:
    '''
    Вставляет в сообщение цифры случайного кода заданной длины.
    Возвращает пару из изменённого сообщения и строки с кодом.
    '''
    digits = [str(randint(0, 9)) for _ in range(code_length)]
    message_characters = list(message_)
    step = (len(message_characters) - 1) // code_length
    for i, digit in enumerate(digits):
        message_characters.insert(  # медленно
            randint(i*step, (i+1)*step - 1), digit
        )

    return ''.join(message_characters), ''.join(digits)


file_to_decompress_path: str
script_directory = dirname(realpath(__file__))
uncompressed_dir_name = 'uncompressed_docx'

if len(argv) >= 2:
    given_filename = argv[1]
    if isabs(given_filename):
        file_to_decompress_path = given_filename
    else:
        file_to_decompress_path = join(script_directory, given_filename)
        warning('Задан относительный путь. Будет распакован файл '
                '\"{file_to_decompress_path}\"')
    if not isfile(file_to_decompress_path):
        fatal('Указан не файл. Скрипт остановлен.')
        exit(3)
else:
    warning('Файл для распаковки не задан. Ищу кандидатов в моём '
            'каталоге.')
    file_to_decompress_candidates = \
        glob(join(script_directory, '*.docx'))
    if len(file_to_decompress_candidates) > 1:
        fatal('Кандидатов для распаковки более одного. Скрипт '
              'остановлен.')
        exit(1)
    elif len(file_to_decompress_candidates) < 1:
        fatal('Кандидатов не найдено. Скрипт остановлен.')
        exit(2)
    file_to_decompress_path = file_to_decompress_candidates.pop()

uncompressed_docx_dir = join(script_directory, uncompressed_dir_name)

if not isdir(uncompressed_docx_dir):
    makedirs(uncompressed_docx_dir)
elif scandir(uncompressed_docx_dir):
    message = 'Каталог для распаковки не пуст. '\
        'Операция может привести к потере данных. Введите цифры '\
        'из этого сообщения, чтобы продолжить.'
    message_with_code, code = sprinkle_in_code(message)
    warning(message_with_code)
    attempts = 3
    while attempts > 0:
        code_entered = input()
        if code_entered == code:
            break
        warning('Код неверный.')
        attempts -= 1
    if attempts <= 0:
        fatal('Слишком много неправильных попыток. Опасная операция не '
              'подтверждена. Скрипт остановлен.')
        exit(4)

file_to_decompress = ZipFile(file_to_decompress_path, 'r')
file_to_decompress.extractall(uncompressed_docx_dir)
file_to_decompress.close()
info('OK')
