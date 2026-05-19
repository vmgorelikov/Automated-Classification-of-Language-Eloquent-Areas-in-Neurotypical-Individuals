from collections import Counter
from collections.abc import Sequence
from typing import Any

import faiss
import joblib
import numpy as np
import polars as pl
from rapidfuzz.distance import Levenshtein
from rapidfuzz.process import cdist
import rustworkx as rx
from rustworkx.visit import BFSVisitor, StopSearch
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.exceptions import NotFittedError
from sklearn.feature_extraction.text import CountVectorizer
from tqdm import tqdm

class FeatureExtractor(BaseEstimator, TransformerMixin):
    def __init__(self, column_names: Sequence[str] | None = None,
                 max_editops: int = 10000,
                 force_use_transcription: bool = False,
                 stop_words: list[str] | None = None,
                 word_list_path: str = '../data/word_frequencies/'
                                       'AranRusi_a.tsv',
                 word_list_cutoff: int | None = None,
                 search_stop_words: list[str] | None = None,
                 word_list_n_candidates: int = 200,
                 word_list_radius: int = 3,
                 ruwordnet_edges_path: str = '../data/ruwordnet/'
                               'polars_edges_dataframe.joblib.xz',
                 ruwordnet_word_mappings_path: str ='../data/ruwordnet/'
                            'polars_word_mapping_dataframe.joblib.xz',
                 ruwordnet_n_candidates: int = 6,
                 ruwordnet_n_best: int = 3,
                 skip_expensive: bool = False):
        '''
        :param column_names: Метки столбцов набора данных, если
            подаётся стуктура данных без них.

        :param max_editops: Максимальное количество выдаваемых в
            качестве признаков отдельных операций редактирования.

        :param force_use_transcription: Использовать ли транскрипцию при
            её остсутствии у части записей. Если `True`, вместо 
            отсутствующих транскрипций используются пустые строки. Если 
            `False`, транскрипции используются только при их наличии у
            всех записей.
        
        :param stop_words: Набор подстрок, которые следует удалить из
            транскриптов перед извлечением признаков.

        :param word_list_path: Путь к TSV файлу, содержащему частотный
            список слов в виде колонок `'words'` со словами и 
            `'Frequency'` — с абсолютной частотностью.

        :param word_list_cutoff: Сколько первых уникальных строк        
            частотного списка слов использовать. Если `None`, то
            используется весь список.

        :param search_stop_words: Набор подстрок, которые следует
            удалить из транскрипта только при сравнении ответов с 
            частотным списком или RuWordNet.

        :param word_list_n_candidates: Количество ближайших кандидатов
            из частотного списка слов для расчёта расстояния
            Левенштейна.

        :param word_list_radius: Количество ближайших слов среди
            кандидатов из частотного списка слов, для которых
            будет посчитана метрика.

        :param ruwordnet_edges_path: Путь к joblib-дампу
            `polars.DataFrame`, содержащего граф в виде двух колонок с 
            целочисленными ID вершин.

        :param ruwordnet_word_mappings_path: Пусть к  joblib-дампу
            `polars.DataFrame`, где ID (неуникальным) в колонке `'id'`
            сопоставляются слова — члены синсетов (тоже неуникальные) в
            колонке `'word'`.

        :param ruwordnet_n_candidates: Количество соседних синсетов, 
            слова которых будут рассмотрены.

        :param ruwordnet_n_best: Количество рассмотренных синсетов,
            результаты рассмотрения которых (расстояние в графе, 
            количество кратчайших путей и расстояние Левенштейна от
            ближайшего по нему слова в синсете до ответа) будут выданы
            как признаки.

        :param skip_expensive: Пропустить ли извлечение признаков по
            RuWordNet и частотному списку слов.
        '''
        self.fit_ = False
        self.column_names = column_names
        self.max_editops = max_editops
        self.force_use_transcription = force_use_transcription
        self.use_transcription = self.force_use_transcription
        self.stop_words = stop_words or ['нрзб']
        self._stop_words_replacements = [''] * len(self.stop_words)
        self.search_stop_words = search_stop_words or ['это']
        self._search_stop_words_replacements = \
                                [''] * len(self.search_stop_words)
        self.word_list_path = word_list_path
        self.word_list_n_candidates = word_list_n_candidates
        self.word_list_radius = word_list_radius
        self.ruwordnet_n_candidates = ruwordnet_n_candidates
        self.ruwordnet_n_best = ruwordnet_n_best
        self.ruwordnet_edges_path = ruwordnet_edges_path
        self.ruwordnet_word_mappings_path = \
                                        ruwordnet_word_mappings_path
        
        self.skip_expensive = skip_expensive

        # TODO: загрузка частотного списка из файла любого формата с
        # именованными колонками
        self.word_list_cutoff = word_list_cutoff

        if not self.skip_expensive:
            self.word_list = pl.read_csv(word_list_path,
                            separator='\t')\
                        .sort('Frequency', descending=True)\
                        .with_columns(pl.col('Frequency')\
                                .log(base=2)\
                                .alias('w_log_Frequency'),
                                pl.col('word')\
                                .fill_null('')\
                                .str.to_lowercase()\
                                .str.replace_all(r'[^а-яё ]', ''))\
                    .filter(pl.col('word').str.len_chars() > 0)\
                    .unique(pl.col('word'))[:word_list_cutoff]
            
            self.word_list_vectorizer = CountVectorizer(dtype=np.int8,
                                                        analyzer='char')
        
            self.word_list_vectors = np.ascontiguousarray(
                                self.word_list_vectorizer\
                                .fit_transform(self.word_list['word'])\
                                .toarray())
        
            self.word_list_nearest_neighbors = \
                            faiss.IndexFlatL2(self.word_list_vectors\
                                            .shape[1])
        
            self.word_list_nearest_neighbors.add(self.word_list_vectors)
            ruwordnet_edges: pl.DataFrame  = \
                joblib.load(ruwordnet_edges_path)
            self.ruwordnet_graph = rx.PyGraph()
            self.ruwordnet_graph.extend_from_edge_list(
                                    ruwordnet_edges.iter_rows())
            del ruwordnet_edges
            self.ruwordnet_word_mappings: pl.DataFrame = joblib\
                                    .load(ruwordnet_word_mappings_path)

    def _clean(self, X: pl.DataFrame) -> pl.DataFrame:
        '''
        Подготавливает колонки с исходными данными: заполняет пропуски
        и очищает `'Response_annot'` от небукв и стопслов.
        '''
        return X\
            .with_columns( # заполнение пропусков
                pl.col('RT_start').fill_null(self.rt_start_mode),
                pl.col('Response_annot')\
                    .fill_null('')\
                    # очистка
                    .str.to_lowercase()\
                    .str.strip_chars()\
                    .str.replace_all(r'[^а-яё ]', '')\
                    .str.replace_many(self.stop_words,
                                      self._stop_words_replacements)\
                    .str.replace_all(r'\s+', ' ')\
                    .str.replace_all('ё', 'е'),
                pl.col('Response_transcription_annot').fill_null('')
            )

    
    def _get_relative_lengths(self, X: pl.DataFrame) -> pl.DataFrame:
        '''
        Рассчитать длины ответа и транскрипции ответа по отношению к
        стимулу.

        :param X: Датафрейм с колонками `'Stimulus'`,
          `'Response_annot'` и `'Response_transcription_annot'`.

        :returns: Новый датафрейм с единственной колонкой 
          `'relative_length'` или с двумя — с ней и с 
          `'relative_length_transcription'`.
        '''
        X = X\
            .with_columns( # относительная длина
                            (pl.col('Response_annot').str.len_chars()/
                            pl.col('Stimulus').str.len_chars())\
                        .fill_null(0)\
                        .alias('relative_length')
            )
        selection: list[str] = ['relative_length']
        if self.use_transcription:
            X = X.with_columns( # относительная длина транскрипции
                (pl.col('Response_transcription_annot').str.len_chars()/
                pl.col('Stimulus').str.len_chars())\
                .fill_null(0)\
                .alias('relative_length_transcription')
            )
            selection.append('relative_length_transcription')
        return X[selection]

    @staticmethod
    def _get_editop_string(type_: str,
                               i_source: int, 
                               i_destination: int,
                               source: str,
                               destination: str) -> str:
            if type_ == 'delete':
                return f'{type_}_{source[i_source]}'
            if type_ == 'insert':
                return f'{type_}_{destination[i_destination]}'
            return f'{type_}_{source[i_source]}'\
                   f'_{destination[i_destination]}'

    def _editop_counts(self, X: pl.DataFrame) -> pl.DataFrame:
        '''
        Считает количество операций редактирования для каждой пары
        символов.

        :param X: Датафрейм со столбцами `'Stimulus'`,
         `'Response_annot'` и, если нужно,
         `'Response_transcription_annot'`

        :returns: Новый датафрейм со столбцами для каждой 
         операции редактирования с каждой парой символов.
        '''
        if not ('Stimulus' in X.columns and\
                'Response_annot' in X.columns and\
                (not self.use_transcription or \
                 'Response_transcription_annot' in X.columns
                 )):
            raise TypeError('Нет ожидаемых колонок для подсчёта отдель'\
                            'ных операций редактирования.')
        new_rows: list[dict[str, int]] = []

        stimuli = X['Stimulus']
        responses = X['Response_annot']
        if self.use_transcription:
            responses_transcription = X['Response_transcription_annot']

        for i in range(X.height):
            pairs: Counter[str] = Counter()
            pairs.update([self._get_editop_string(
                            type_, i1, i2,
                            stimuli[i],
                            responses[i]) \
                        for type_, i1, i2 in Levenshtein.editops(
                            stimuli[i],
                            responses[i])]
                        )
            
            if self.use_transcription:
                pairs.update(['T' + self._get_editop_string(
                                type_, i1, i2,
                                stimuli[i],
                                responses_transcription[i])\
                            for type_, i1, i2 in Levenshtein.editops(
                                stimuli[i],
                                responses_transcription[i])]
                            )
                
            new_rows.append(dict(pairs))

        output = pl.from_dicts(new_rows,
                               infer_schema_length=2**32)
        
        # это может быть полезно
        output = output.select(sorted(output.columns))

        return output
    

    def _get_word_list_metrics(self, X: pl.DataFrame) -> pl.DataFrame:
        pairs = X.select(['Response_annot', 'Stimulus']).unique()

        fallback_frequency = self.word_list['w_log_Frequency'].mode()[0]
        
        pairs_with_frequencies = pairs.join(
            self.word_list.select(['word', 'w_log_Frequency']),
            left_on='Stimulus', right_on='word', how='left'
        ).with_columns(
            pl.col('w_log_Frequency').fill_null(fallback_frequency)
        )

        responses_clean = pairs_with_frequencies['Response_annot']\
                            .str.replace_many(
                                self.search_stop_words,
                                self._search_stop_words_replacements
                            )

        query_vectors = np.ascontiguousarray(
                                            self.word_list_vectorizer\
                                            .transform(responses_clean)\
                                            .toarray()
                                            )
        
        _, candidate_indices = self.word_list_nearest_neighbors\
                                .search(query_vectors,
                                        k=self.word_list_n_candidates)

        words = self.word_list['word']
        
        radius = self.word_list_radius
        all_distances = np.empty((responses_clean.len(), radius),
                                        dtype=np.int8)
        all_frequency_differences = np.empty((responses_clean.len(),
                                              radius))
        
        for i in range(responses_clean.len()):
            if not responses_clean[i]: # для пустых ответов
                all_distances[i, :] = 127
                all_frequency_differences[i, :] = 127.
                continue
            distances = (cdist([responses_clean[i]],
                        self.word_list['word'][candidate_indices[i]]) \
                        / (len(responses_clean[i]))).squeeze()
                                
            frequency_penalties = \
             np.abs(
              self.word_list['w_log_Frequency'][candidate_indices[i]]\
                                                           .to_numpy() -
              pairs_with_frequencies['w_log_Frequency'][i]
            )
            distances.partition(radius - 1)
            indices_to_include = np.argsort(distances[:radius],
                                            kind='stable')
            all_distances[i] = distances[indices_to_include]
            all_frequency_differences[i] = frequency_penalties\
                                               [indices_to_include]

        distance_column_names = [f'word_list_distance_{i}'
                                 for i in range(radius)]
        
        frequency_difference_column_names = \
                                [f'word_list_frequency_difference_{i}'
                                 for i in range(radius)]
        
        results = pl.DataFrame(all_distances,
                              schema=distance_column_names,
                              orient='row').hstack(
                  pl.DataFrame(all_frequency_differences,
                              schema=frequency_difference_column_names,
                              orient='row')  
                              ).hstack(pairs)
        X = X.join(results,
                   on=['Response_annot', 'Stimulus'],
                   how='left')\
            .select(distance_column_names + \
                    frequency_difference_column_names)
        null_count_ = X.null_count()
        if null_count_.sum_horizontal().sum() > 0:
            print(null_count_)
        return X

    class _KMaxVisitor(BFSVisitor):
        def __init__(self, stimulus_id, k):
            self.k = k
            self.stimulus_id = stimulus_id
            self.distances = {stimulus_id: 0}
            self.path_counts = {stimulus_id: 1}

        def tree_edge(self, edge):
            source, target, _ = edge
                
            self.distances[target] = self.distances[source] + 1
            self.path_counts[target] = self.path_counts[source]
            if max(len(self.distances),
                   len(self.path_counts)) >= self.k + 1:
                    if len(self.distances) != len(self.path_counts):
                        raise ValueError('!')
                    raise StopSearch()

        def non_tree_edge(self, edge):
            source, target, _ = edge
            self.path_counts[target] += self.path_counts[source]

        def discover_vertex(self, v):
            if v == self.stimulus_id:
                return

    def _get_ruwordnet_metrics_II(self, X: pl.DataFrame
                                                )\
                                            -> pl.DataFrame:
        # это остаток предыдущего, проблемного решения; но может такое
        # разбиение логики на две функции всё ещё полезно
        result = pl.DataFrame()
        for id, response in tqdm(
                                X[['id', 'Response_annot']].iter_rows()
                                ):
            visitor = self._KMaxVisitor(id, self.ruwordnet_n_candidates)
            rx.bfs_search(self.ruwordnet_graph, [id], visitor)
            # найденным кандидатам сопоставляются строки со словами в
            # синсетах; слов обычно больше одного
            candidates = pl.from_dict({
                    'id':  visitor.distances.keys(),
                    'graph_distance': visitor.distances.values(),
                    'n_paths':  visitor.path_counts.values()})\
                .join(
                                self.ruwordnet_word_mappings,
                                'id', 'left')
            # для слов считаются расстояния Левенштейна по отношению
            # к Response_annot; из синонимов выбираются те с наименьшим
            # расстоянием; затем синсеты сортируются по расстоянию
            # Левенштейна и берётся заданное количество ближайших;
            # id синсета отбрасывается
            candidates = candidates\
                .with_columns(levenshtein_distance =\
                pl.Series(cdist([response],
                                candidates['word'],
                                scorer=Levenshtein.distance
                            ).squeeze()))\
                .sort('levenshtein_distance')\
                .unique(subset='id', keep='first', maintain_order=True)
            
            candidates = candidates\
                .head(self.ruwordnet_n_best)\
                .drop('id', 'word')\
                .with_row_index()\
                .unpivot(index='index')\
                .select(
                    pl.col('index'),
                    name = pl.format('{}_{}', pl.col('variable'),
                                     pl.col('index')),
                    value = pl.col('value')
                )\
                .pivot(index='index', on='name', values='value')\
                .drop('index')\
                .select(pl.all()\
                        .forward_fill()\
                        .backward_fill()\
                        .first())
            result = pl.concat([result, candidates], how='diagonal')
        
        return result

    def _get_ruwordnet_metrics(self, X: pl.DataFrame) -> pl.DataFrame:
        X = X.with_columns(pl.col('Response_annot')\
                           .str.replace_many(
                                self.search_stop_words,
                                self._search_stop_words_replacements
                            )\
                            .str.strip_chars())\
             .with_row_index('row_index')\
             .join(
                self.ruwordnet_word_mappings\
                    .select(['word', 'id']),
                left_on='Stimulus', right_on='word', how='left'
            )
        
        uniques = X.select(['id', 'Response_annot']).unique()
        uniques = pl.concat([uniques,
                            self._get_ruwordnet_metrics_II(uniques)],
                            how='horizontal')

        X = X[['id', 'row_index', 'Stimulus', 'Response_annot']]\
            .join(uniques,
                  on=['id', 'Response_annot'], how='left')\
            .with_columns(pl.min_horizontal(r'^graph_distance_.+$')\
                          .alias('graph_distance_min'))\
            .sort('row_index', 'graph_distance_min')\
            .unique(subset='row_index',
                    keep='first',
                    maintain_order=True)\
            .with_columns(pl.col(r'^levenshtein_distance_.+$') /\
                          pl.col('Stimulus').str.len_chars())\
            .drop('row_index', 'Stimulus', 'Response_annot', 'id')\
            .with_columns(
                pl.col(r'^levenshtein_distance_.+$').fill_null(127),
                pl.col(r'^graph_distance_.+$').fill_null(127),
                pl.col(r'^n_paths_.+$').fill_null(0),
            )
        
        null_count_ = X.null_count()
        if null_count_.sum_horizontal().sum() > 0:
            print(null_count_.unpivot())

        return X.select(pl.all().name.prefix("ruwordnet_"))

    def fit(self, X: pl.DataFrame | np.ndarray, y: Any = None):
        if type(X) != pl.DataFrame:
            X = pl.from_numpy(X, self.column_names)

        self.use_transcription = self.force_use_transcription or not\
            X.get_column('Response_transcription_annot').is_null().any()
        self.rt_start_mode = X['RT_start'].mode()
        X = self._clean(X)
        # определение самых частотных операций в датасете, на котором
        # преобразователь фиттится
        X = self._editop_counts(X)
        self.top_editop_columns: list[str] = \
                    X.select(pl.all()\
                        .exclude(pl.String)\
                        .sum()
                    )\
                    .unpivot()\
                    .sort('value', descending=True)\
                    .head(self.max_editops)\
                    .get_column('variable')\
                    .to_list()

        self.fit_ = True
        return self

    def transform(self, X: pl.DataFrame | np.ndarray):
        if not self.fit_:
            raise NotFittedError
        if type(X) != pl.DataFrame:
            X = pl.from_numpy(X, self.column_names)

        X = self._clean(X)
        relative_lengths = self._get_relative_lengths(X)

        counts = self._editop_counts(X)

        
        # нормализованные количества операций
        prefixes = ['Tdelete', 'Tinsert', 'Treplace',
                    'delete', 'insert', 'replace']
        stimulus_lengths = X.get_column('Stimulus').str.len_chars()
        normalized_total_editops = []
        for prefix in prefixes:
            columns_to_sum = [c
                           for c in counts.columns
                           if c.startswith(f'{prefix}_')]
            if columns_to_sum:
                column = \
                (counts.select(columns_to_sum)\
                        .sum_horizontal() /
                          stimulus_lengths)\
                    .alias(prefix + '_normalized_total')
                normalized_total_editops.append(column)

        normalized_total_editops = \
            pl.DataFrame(normalized_total_editops)
        

        counts = counts.with_columns(
                [pl.lit(0, dtype=pl.Int64).alias(c) 
                for c in self.top_editop_columns
                if c not in counts.columns])\
            .select(self.top_editop_columns).fill_null(0)
        
        all_feature_dataframes = [X,
                relative_lengths,
                normalized_total_editops
                ]

        if not self.skip_expensive:
            word_list_metrics = self._get_word_list_metrics(X)
            ruwordnet_metrics = self._get_ruwordnet_metrics(X)
            all_feature_dataframes += [word_list_metrics,
                                       ruwordnet_metrics]

        all_feature_dataframes += [counts]
        X = pl.concat(all_feature_dataframes,
                how='horizontal') \
            .drop(pl.selectors.string())
        # print(X.columns)
        return X
