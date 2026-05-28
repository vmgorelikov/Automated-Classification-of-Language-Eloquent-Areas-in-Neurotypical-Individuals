'''
Пользовательский интерфейс автоматического классификатора речевых зон

:Authors: В. М. Гореликов
'''
import sys
import os.path
from types import FunctionType
import logging
from logging import warning, fatal, info



logging.basicConfig(level=logging.INFO)

if len(sys.argv) < 2:
    warning('Использование: python main.py <входной файл> [параметры]')
    fatal('Ничего не задано.')
    exit(1)

input_filename = sys.argv[1]
if not os.path.isfile(input_filename):
    fatal(f'{input_filename} — не файл.')
    exit(1)

import polars as pl # импортируем по мере необходимости, чтобы
# пользователь не ждал, а сразу получал ошибку

polars_readers: dict[str, FunctionType] = {
    'csv': pl.read_csv,
    'tsv': pl.read_csv,
    'txt': pl.read_csv,
    'parquet': pl.read_parquet,
    'arrow': pl.read_ipc,
    'ipc': pl.read_ipc,
    'feather': pl.read_ipc,
    'avro': pl.read_avro,
    'json': pl.read_json,
    'ndjson': pl.read_ndjson,
    'jsonl': pl.read_ndjson,
    'xlsx': pl.read_excel,
    'xlsm': pl.read_excel,
    'ods': pl.read_ods,
}

dataset: pl.DataFrame | None = None
try:
    dataset =\
        polars_readers[input_filename.split('.')[-1]](input_filename)
except KeyError as e:
    warning('Не получается определить тип файла. Перебираю...')
    for reader in polars_readers.values():
        try:
            dataset = reader(input_filename)
        except Exception:
            pass
        if dataset is not None:
            break
    if dataset is None:
        fatal('Не удалось подобрать тип файла.')
        exit(1)
except (OSError, PermissionError) as e:
    fatal('Доступ к файлу невозможен:')
    fatal(e)
    exit(1)
except Exception:
    fatal('Произошла неизвестая ошибка.')
    exit(1)

if dataset is None:
    fatal('Произошла неизвестая ошибка. (2)')
    exit(1)

missing_columns = {'RT_start', 'Stimulus', 'Response_annot'} - \
                    set(dataset.columns)

if missing_columns:
    fatal('Во входном файле нет колонок ' + ', '.join(missing_columns) +
          ', может быть полезным проверить правильность регистра их '
          'заглавий.')
    exit(1)


from feature_extractor import FeatureExtractor

feature_extractor = FeatureExtractor(
        stop_words=('нрзб',),
        search_stop_words=('это',),
        word_list_n_candidates=200,
        word_list_radius=10,
        ruwordnet_n_candidates=200,
        ruwordnet_n_best=10
    )


import joblib

feature_extractor.rt_start_mode = 766
feature_extractor.top_editop_columns =\
    joblib.load('../data/models/train_top_editop_columns.joblib.xz')
feature_extractor.fit_ = True

features = feature_extractor.transform(dataset)

import catboost

classifier = catboost.CatBoostClassifier()\
                    .load_model('../data/models/catboost.cbm')

predictions = classifier.predict(features)

input_filename_by_dots = input_filename.split('.')

output_filename = '.'.join(input_filename_by_dots[:-1]) + \
                    '_predictions' + \
                    '.' + input_filename_by_dots[-1]

polars_writers: dict[str, str] = {
    'csv': 'write_csv',
    'tsv': 'write_csv',
    'txt': 'write_csv',
    'parquet': 'write_parquet',
    'arrow': 'write_ipc',
    'ipc': 'write_ipc',
    'feather': 'write_ipc',
    'avro': 'write_avro',
    'json': 'write_json',
    'ndjson': 'write_ndjson',
    'jsonl': 'write_ndjson',
    'xlsx': 'write_excel',
    'xlsm': 'write_excel',
    'arrow_table': 'to_arrow', 
}

import json

error_type_ids = pl.read_json('../data/processed/error_type_ids.json').unpivot()

predictions_with_names = pl.DataFrame({
                    'error_type_label': pl.Series(predictions.ravel())
                    }).join(error_type_ids,
                            how='left',
                            left_on='error_type_label',
                            right_on='value')\
                        .rename({'variable': 'error_type_name'})

getattr(
    dataset.hstack(predictions_with_names),
                     polars_writers[input_filename_by_dots[-1]])\
                    (output_filename)

info('OK')
