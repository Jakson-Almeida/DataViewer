"""
Módulo para gerenciamento e extração de dados de arquivos HDF5.

Este módulo fornece funcionalidades para extrair dados de arquivos HDF5
estruturados com grupos de experimentos e amostras, convertendo-os em
DataFrames pandas para análise posterior.
"""

import h5py
import pandas as pd
import numpy as np
import json


def hdf5_2_df(caminho_h5, amostras_selecionadas):
    """
    Extrai dados de amostras de um arquivo HDF5 e retorna um DataFrame consolidado.

    Esta função lê um arquivo HDF5 contendo grupos de amostras organizados por
    experimento. Cada amostra contém datasets (séries temporais ou espectros)
    e metadados associados. Os dados são consolidados em um único DataFrame
    onde cada linha representa uma amostra com seus respectivos datasets como colunas.

    Args:
        caminho_h5 (str): Caminho absoluto ou relativo para o arquivo HDF5.
        amostras_selecionadas (list): Lista de caminhos de amostras no formato
            '/experimento/amostra' a serem extraídas do arquivo HDF5.

    Returns:
        pd.DataFrame: DataFrame consolidado contendo:
            - Metadados: data, identificador, mensurando, amostra_id,
              valor_referencia, info_amostra
            - Datasets: Colunas dinâmicas contendo as séries de dados de cada amostra
            - Índice resetado e sequencial

    Raises:
        FileNotFoundError: Se o arquivo HDF5 não existir.
        KeyError: Se a estrutura do arquivo não corresponder ao esperado.

    Notes:
        - Amostras sem datasets são ignoradas silenciosamente.
        - Valores escalares são automaticamente repetidos para corresponder ao
          comprimento dos arrays multidimensionais.
        - Aviso será impresso para amostras não encontradas no arquivo.

    Example:
        >>> df = extrair_dados_para_dataframe(
        ...     'data/medidas.h5',
        ...     ['/experimento_01/amostra_A', '/experimento_01/amostra_B']
        ... )
        >>> print(df.shape)
        (N_amostras, N_colunas)
    """
    dataframe_list = []

    # Abre o arquivo HDF5 em modo leitura
    with h5py.File(caminho_h5, 'r') as h5_file:
        # Itera sobre cada amostra selecionada
        for caminho_amostra in amostras_selecionadas:
            # Valida existência da amostra no arquivo HDF5
            if caminho_amostra not in h5_file:
                print(f"Aviso: {caminho_amostra} não encontrado.")
                continue
                
            # Acessa o grupo da amostra e extrai seu nome
            grp_amostra = h5_file[caminho_amostra]
            nome_amostra = grp_amostra.name.split('/')[-1]
            
            # Acessa o grupo pai (experimento) para extrair seus atributos
            grp_experimento = grp_amostra.parent
            attrs = dict(grp_experimento.attrs)
            
            def load_json_attr(attr_name):
                """
                Carrega e deserializa um atributo JSON do grupo de experimento.

                Se o atributo armazenado for uma string JSON, ela é desserializada.
                Caso contrário, retorna o valor como está ou um dicionário vazio
                se não existir.

                Args:
                    attr_name (str): Nome do atributo a ser carregado do grupo.

                Returns:
                    dict or any: Objeto Python desserializado do JSON ou valor padrão vazio.
                """
                val = attrs.get(attr_name, {})
                return json.loads(val) if isinstance(val, str) else val
            
            # Carrega os mapeamentos JSON de amostras e valores de referência
            amostras_map = load_json_attr('amostras')
            ref_map = load_json_attr('valores_referencia')

            # Extrai todos os datasets numéricos da amostra para um dicionário
            # Cada dataset representa uma série temporal ou espectro de medição
            datasets = {k: v[()] for k, v in grp_amostra.items() if isinstance(v, h5py.Dataset)}
            
            if not datasets:
                continue  # Ignora amostras sem dados
                
            # Determina o comprimento dos arrays usando o primeiro dataset como referência
            # Isso garante consistência entre datasets de diferentes tipos
            primeiro_ds = list(datasets.keys())[0]
            N = len(datasets[primeiro_ds])
            
            # Constrói um dicionário consolidado com metadados + datasets
            # Os metadados são associados à amostra específica
            row_data = {
                'data': attrs.get('data'),
                'identificador': attrs.get('identificador'),
                'mensurando': attrs.get('mensurando'),
                'amostra_id': nome_amostra,
                'valor_referencia': ref_map.get(nome_amostra),
                'info_amostra': amostras_map.get(nome_amostra)
            }
            row_data.update(datasets)

            # Transforma os dados em um DataFrame, replicando valores escalares
            # para corresponder ao comprimento dos arrays multidimensionais (N linhas)
            sub_df = pd.DataFrame({
                k: ([v] * N if not isinstance(v, (list, np.ndarray)) else v) 
                for k, v in row_data.items()
            })
            
            dataframe_list.append(sub_df)

    # Consolida todos os DataFrames de amostras em uma única tabela
    # Retorna um DataFrame vazio se nenhuma amostra foi processada com sucesso
    return pd.concat(dataframe_list, ignore_index=True) if dataframe_list else pd.DataFrame()