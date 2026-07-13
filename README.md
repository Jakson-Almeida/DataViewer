# DataViewer

Visualizador interativo de arquivos HDF5 do pipeline COPASA. Permite navegar a estrutura do arquivo, selecionar amostras e plotar séries/espectros a partir de um DataFrame consolidado.

## Estrutura

| Arquivo | Função |
|---------|--------|
| `visualizer.py` | Aplicação gráfica (PyQt5) — árvore HDF5, tabela e gráficos |
| `dataframe_manager.py` | Extração de amostras HDF5 para `pandas.DataFrame` |

## Requisitos

- Python 3.8+
- Dependências:

```bash
pip install h5py pandas numpy PyQt5 matplotlib seaborn
```

## Como executar

```bash
python visualizer.py
```

1. Clique em **Abrir Arquivo .h5** e selecione o arquivo.
2. Marque na árvore os grupos de amostra desejados (caminho `/experimento/amostra`).
3. Clique em **Processar Selecionados**.
4. Ajuste os eixos **X**, **Y** e **Cor** nos comboboxes para atualizar o gráfico.

O processamento roda em thread separada (`DataWorker`) para não travar a interface.

## Formato esperado do HDF5

```
/
└── experimento_XX/          # atributos: data, identificador, mensurando,
    │                        # amostras (JSON), valores_referencia (JSON)
    ├── amostra_A/
    │   └── datasets...      # séries temporais / espectros (h5py.Dataset)
    └── amostra_B/
        └── datasets...
```

Atributos do grupo de experimento:

- `data`, `identificador`, `mensurando`
- `amostras` — mapa JSON nome → info da amostra
- `valores_referencia` — mapa JSON nome → valor de referência

## API: `hdf5_2_df`

```python
from dataframe_manager import hdf5_2_df

df = hdf5_2_df(
    'data/medidas.h5',
    ['/experimento_01/amostra_A', '/experimento_01/amostra_B']
)
```

**Retorno:** DataFrame com metadados (`data`, `identificador`, `mensurando`, `amostra_id`, `valor_referencia`, `info_amostra`) e colunas dinâmicas para cada dataset. Valores escalares são repetidos para alinhar ao comprimento dos arrays.

Amostras inexistentes geram aviso; amostras sem datasets são ignoradas.
