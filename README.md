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
2. Marque sensores, experimentos ou amostras na árvore (a seleção propaga aos filhos).
3. Clique em **Processar Selecionados** — só grupos que contêm datasets (nível amostra) são processados.
4. Ajuste os eixos **X**, **Y**, **Cor** e o **Tipo** de gráfico (Linha, Dispersão, Barras).
5. Use **Mostrar tabela** para exibir ou ocultar a prévia de dados abaixo do gráfico.
6. Use **Exportar gráfico** para salvar PNG/PDF/SVG/JPEG.

O processamento roda em thread separada (`DataWorker`) para não travar a interface.

## Formato esperado do HDF5

```
/
└── SENSOR_ID/                 # attrs do sensor (opcional)
    └── EXP_ID/                # attrs: data, identificador, mensurando,
        │                      # amostras (JSON), valores_referencia (JSON)
        ├── 1/                 # amostra
        │   └── datasets...    # Timestamps, resonant_wl_*, etc.
        └── 2/
            └── datasets...
```

Também funciona o layout mais simples `/experimento/amostra`. Em ambos os casos, uma **amostra** é um grupo que contém um ou mais `h5py.Dataset`.

Atributos do grupo de experimento:

- `data`, `identificador`, `mensurando`
- `amostras` — mapa JSON nome → info da amostra
- `valores_referencia` — mapa JSON nome → valor de referência

## API: `hdf5_2_df`

```python
from dataframe_manager import hdf5_2_df

df = hdf5_2_df(
    'test_data/data_wl.h5',
    ['/INT_NH3_001/EXP_1/1', '/INT_NH3_001/EXP_1/7']
)
```

**Retorno:** DataFrame com metadados (`data`, `identificador`, `mensurando`, `amostra_id`, `valor_referencia`, `info_amostra`) e colunas dinâmicas para cada dataset. Valores escalares são repetidos para alinhar ao comprimento dos arrays.

Amostras inexistentes geram aviso; amostras sem datasets são ignoradas.
