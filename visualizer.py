import sys
import json
from pathlib import Path
from datetime import datetime
import h5py
import pandas as pd
import numpy as np
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QKeySequence
from PyQt5.QtWidgets import (QApplication, QMainWindow, QTreeWidget, QTreeWidgetItem, 
                             QHBoxLayout, QVBoxLayout, QPushButton, QWidget, QFileDialog, 
                             QTreeWidgetItemIterator, QMessageBox, QTableWidget, QTableWidgetItem, 
                             QSplitter, QComboBox, QLabel, QCheckBox, QTextEdit, QShortcut,
                             QDialog, QDialogButtonBox, QListWidget, QListWidgetItem, QFormLayout,
                             QGroupBox, QAbstractItemView)
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import seaborn as sns
from dataframe_manager import hdf5_2_df
from tara import PROTOCOLOS, aplicar_tara, listar_amostras_unicas, remover_colunas_rel


class TaraDialog(QDialog):
    """Modal de configuração do protocolo de tara."""

    def __init__(self, df, parent=None, protocolo_atual="agua_anterior", filtro_agua="água di"):
        super().__init__(parent)
        self.setWindowTitle("Configurar tara")
        self.resize(520, 480)
        self.setModal(True)

        layout = QVBoxLayout(self)

        intro = QLabel(
            "Define como subtrair a baseline (tara) das features.\n"
            "Serão criadas colunas rel_<feature> para plotagem."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        self.cb_protocolo = QComboBox()
        for key, label in PROTOCOLOS.items():
            self.cb_protocolo.addItem(label, key)
        idx = self.cb_protocolo.findData(protocolo_atual)
        if idx >= 0:
            self.cb_protocolo.setCurrentIndex(idx)
        self.cb_protocolo.currentIndexChanged.connect(self._atualizar_estado_manual)
        form.addRow("Protocolo:", self.cb_protocolo)

        self.ed_filtro = QComboBox()
        self.ed_filtro.setEditable(True)
        self.ed_filtro.addItems(["água di", "agua di", "Água DI"])
        self.ed_filtro.setCurrentText(filtro_agua)
        form.addRow("Filtro Água DI:", self.ed_filtro)
        layout.addLayout(form)

        grupo = QGroupBox("Amostras de tara (seleção manual)")
        g_layout = QVBoxLayout(grupo)
        self.lista = QListWidget()
        self.lista.setSelectionMode(QAbstractItemView.MultiSelection)
        amostras = listar_amostras_unicas(df)
        for _, row in amostras.iterrows():
            ident = row.get("identificador", "")
            aid = row.get("amostra_id", "")
            info = row.get("info_amostra", "")
            ref = row.get("valor_referencia", "")
            texto = f"{ident} / {aid}: {info} | ref={ref}"
            item = QListWidgetItem(texto)
            item.setData(Qt.UserRole, (str(ident), str(aid)))
            self.lista.addItem(item)
        g_layout.addWidget(self.lista)
        dica = QLabel("Usado apenas no protocolo \"Seleção manual\".")
        dica.setStyleSheet("color: gray;")
        g_layout.addWidget(dica)
        layout.addWidget(grupo)

        buttons = QDialogButtonBox()
        self.btn_aplicar = buttons.addButton("Aplicar tara", QDialogButtonBox.AcceptRole)
        self.btn_remover = buttons.addButton("Remover tara", QDialogButtonBox.ActionRole)
        self.btn_cancelar = buttons.addButton(QDialogButtonBox.Cancel)
        self.btn_aplicar.clicked.connect(self.accept)
        self.btn_remover.clicked.connect(self._marcar_remover)
        self.btn_cancelar.clicked.connect(self.reject)
        layout.addWidget(buttons)

        self.remover = False
        self._atualizar_estado_manual()

    def _marcar_remover(self):
        self.remover = True
        self.accept()

    def _atualizar_estado_manual(self):
        manual = self.cb_protocolo.currentData() == "manual"
        self.lista.setEnabled(manual)

    def configuracao(self):
        return {
            "remover": self.remover,
            "protocolo": self.cb_protocolo.currentData(),
            "filtro_agua": self.ed_filtro.currentText().strip() or "água di",
            "amostras_manuais": [
                item.data(Qt.UserRole)
                for item in self.lista.selectedItems()
            ],
        }


class DataWorker(QThread):
    finished = pyqtSignal(pd.DataFrame)
    error = pyqtSignal(str)

    def __init__(self, caminho_h5, selecionados):
        super().__init__()
        self.caminho_h5 = caminho_h5
        self.selecionados = selecionados

    def run(self):
        try:
            df = hdf5_2_df(self.caminho_h5, self.selecionados)
            self.finished.emit(df)
        except Exception as e:
            self.error.emit(str(e))

class H5Visualizer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Visualizador HDF5 - Pipeline COPASA")
        self.resize(1200, 700)
        
        # Widget principal e layout horizontal divisor
        main_splitter = QSplitter(Qt.Horizontal)
        self.setCentralWidget(main_splitter)
        
        # ==========================================
        # PAINEL ESQUERDO: Estrutura & Controles
        # ==========================================
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        
        left_splitter = QSplitter(Qt.Vertical)

        # Árvore hierárquica
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Estrutura do HDF5"])
        self.tree.itemChanged.connect(self.handle_item_changed)
        self.tree.itemSelectionChanged.connect(self.atualizar_metadados)
        self.tree.setFocusPolicy(Qt.StrongFocus)
        esc_arvore = QShortcut(QKeySequence(Qt.Key_Escape), self.tree)
        esc_arvore.setContext(Qt.WidgetWithChildrenShortcut)
        esc_arvore.activated.connect(self.limpar_selecao_arvore)
        left_splitter.addWidget(self.tree)

        # Painel de metadados do nó selecionado
        meta_container = QWidget()
        meta_layout = QVBoxLayout(meta_container)
        meta_layout.setContentsMargins(0, 0, 0, 0)
        meta_layout.addWidget(QLabel("Metadados"))
        self.meta_view = QTextEdit()
        self.meta_view.setReadOnly(True)
        self.meta_view.setPlaceholderText("Abra um arquivo .h5 para ver informações do arquivo.")
        font = QFont("Consolas", 9)
        if not font.exactMatch():
            font = QFont("Courier New", 9)
        self.meta_view.setFont(font)
        meta_layout.addWidget(self.meta_view)
        left_splitter.addWidget(meta_container)
        left_splitter.setSizes([420, 220])

        left_layout.addWidget(left_splitter)
        
        # Botões embaixo e lado a lado (Layout Horizontal)
        buttons_layout = QHBoxLayout()
        self.btn_abrir = QPushButton("Abrir Arquivo .h5")
        self.btn_abrir.clicked.connect(self.abrir_arquivo)
        
        self.btn_analisar = QPushButton("Processar Selecionados")
        self.btn_analisar.clicked.connect(self.iniciar_analise)
        
        buttons_layout.addWidget(self.btn_abrir)
        buttons_layout.addWidget(self.btn_analisar)
        left_layout.addLayout(buttons_layout)

        # Tara em linha própria: não compete com a barra do gráfico
        self.btn_tara = QPushButton("Configurar tara…")
        self.btn_tara.setEnabled(False)
        self.btn_tara.setToolTip("Aplica baseline (Água DI / amostra anterior / manual) após processar dados.")
        self.btn_tara.clicked.connect(self.abrir_dialogo_tara)
        left_layout.addWidget(self.btn_tara)

        main_splitter.addWidget(left_container)
        
        # ==========================================
        # PAINEL DIREITO: Gráfico & Visualização
        # ==========================================
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        
        # --- IMPLEMENTAÇÃO DOS TODOS (COMBOBOXES) ---
        controls_layout = QHBoxLayout()
        
        controls_layout.addWidget(QLabel("Eixo X:"))
        self.cb_x = QComboBox()
        self.cb_x.currentIndexChanged.connect(self.atualizar_grafico)
        controls_layout.addWidget(self.cb_x)
        
        controls_layout.addWidget(QLabel("Eixo Y:"))
        self.cb_y = QComboBox()
        self.cb_y.currentIndexChanged.connect(self.atualizar_grafico)
        controls_layout.addWidget(self.cb_y)
        
        controls_layout.addWidget(QLabel("Cor:"))
        self.cb_color = QComboBox()
        self.cb_color.currentIndexChanged.connect(self.atualizar_grafico)
        controls_layout.addWidget(self.cb_color)

        controls_layout.addWidget(QLabel("Tipo:"))
        self.cb_tipo = QComboBox()
        self.cb_tipo.addItems(["Linha", "Dispersão", "Barras"])
        self.cb_tipo.currentIndexChanged.connect(self.atualizar_grafico)
        controls_layout.addWidget(self.cb_tipo)

        self.chk_tabela = QCheckBox("Mostrar tabela")
        self.chk_tabela.setChecked(True)
        self.chk_tabela.toggled.connect(self.alternar_tabela)
        controls_layout.addWidget(self.chk_tabela)

        self.btn_exportar = QPushButton("Exportar gráfico")
        self.btn_exportar.clicked.connect(self.exportar_grafico)
        controls_layout.addWidget(self.btn_exportar)
        
        right_layout.addLayout(controls_layout)
        
        # Canvas do Matplotlib para plotagem
        self.fig = Figure()
        self.canvas = FigureCanvas(self.fig)
        self.ax = self.fig.add_subplot(111)
        self.fig.tight_layout()
        
        # Tabela para visualizar prévia dos dados coletados
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(['Data', 'Identificador', 'Mensurando', 'Amostra ID', 'Ref', 'Info'])
        
        # Dividir o espaço da direita verticalmente entre gráfico e tabela
        self.right_splitter = QSplitter(Qt.Vertical)
        self.right_splitter.addWidget(self.canvas)
        self.right_splitter.addWidget(self.table)
        self.right_splitter.setSizes([450, 250])
        self._splitter_sizes_com_tabela = [450, 250]
        
        right_layout.addWidget(self.right_splitter)
        main_splitter.addWidget(right_container)
        
        # Ajuste de proporção inicial (Painel esquerdo: 1, Painel direito: 2)
        main_splitter.setSizes([400, 800])
        
        self.caminho_atual = None
        self.df_bruto = None  # DataFrame original pós-processamento
        self.df_atual = None  # DataFrame de trabalho (pode incluir rel_*)
        self._tara_protocolo = "agua_anterior"
        self._tara_filtro = "água di"

    def limpar_selecao_arvore(self):
        """Remove a seleção da árvore (Esc) e volta a info do arquivo nos metadados."""
        self.tree.clearSelection()

    def handle_item_changed(self, item, column):
        self.tree.blockSignals(True)
        state = item.checkState(0)
        self.update_children_state(item, state)
        self.tree.blockSignals(False)

    def update_children_state(self, parent_item, state):
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            child.setCheckState(0, state)
            self.update_children_state(child, state)

    def abrir_arquivo(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Selecione o arquivo HDF5", "", "HDF5 (*.h5)")
        if file_path:
            self.caminho_atual = file_path
            self.tree.clear()
            self.df_bruto = None
            self.df_atual = None
            self.btn_tara.setEnabled(False)
            self.popular_tree(file_path)
            self.exibir_info_arquivo()

    def popular_tree(self, path):
        with h5py.File(path, 'r') as f:
            def add_nodes(parent_item, group):
                for name, obj in group.items():
                    item = QTreeWidgetItem([name])
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(0, Qt.Unchecked)
                    item.setData(0, Qt.UserRole, obj.name)
                    
                    parent_item.addChild(item)
                    if isinstance(obj, h5py.Group):
                        add_nodes(item, obj)
            
            add_nodes(self.tree.invisibleRootItem(), f)

    def exibir_info_arquivo(self):
        """Mostra nome, caminho e data de modificação do HDF5 carregado."""
        if not self.caminho_atual:
            self.meta_view.clear()
            return

        path = Path(self.caminho_atual)
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
            data_mod = mtime.strftime("%d/%m/%Y %H:%M:%S")
            tamanho = path.stat().st_size
            if tamanho >= 1_048_576:
                tam_txt = f"{tamanho / 1_048_576:.2f} MB"
            elif tamanho >= 1024:
                tam_txt = f"{tamanho / 1024:.1f} KB"
            else:
                tam_txt = f"{tamanho} bytes"
        except OSError as e:
            data_mod = f"(indisponível: {e})"
            tam_txt = "—"

        texto = "\n".join([
            "[Arquivo HDF5]",
            "",
            f"nome: {path.name}",
            f"caminho: {path.resolve()}",
            f"modificado em: {data_mod}",
            f"tamanho: {tam_txt}",
            "",
            "Selecione um sensor, experimento ou amostra na árvore",
            "para ver os metadados do nó.",
        ])
        self.meta_view.setPlainText(texto)

    @staticmethod
    def _formatar_attr(valor):
        """Normaliza atributo HDF5 para texto legível."""
        if isinstance(valor, bytes):
            valor = valor.decode("utf-8", errors="replace")
        if isinstance(valor, np.ndarray):
            valor = valor.tolist()
        if isinstance(valor, str):
            try:
                parsed = json.loads(valor)
                return parsed
            except (json.JSONDecodeError, TypeError):
                return valor
        return valor

    def _texto_metadados_grupo(self, grupo, titulo, amostra_id=None):
        linhas = [f"[{titulo}] {grupo.name}", ""]
        if len(grupo.attrs) == 0:
            linhas.append("(sem atributos neste grupo)")
            return "\n".join(linhas)

        attrs = {k: self._formatar_attr(grupo.attrs[k]) for k in grupo.attrs}

        # Campos principais primeiro, se existirem
        prioridade = [
            "identificador", "sensor_id", "nome", "mensurando", "data",
            "data_fabricacao", "objetivo", "notas", "lambda_res",
        ]
        usados = set()
        for chave in prioridade:
            if chave in attrs:
                linhas.append(f"{chave}: {attrs[chave]}")
                usados.add(chave)

        # Mapas de amostras / referências
        amostras = attrs.get("amostras")
        refs = attrs.get("valores_referencia")
        if isinstance(amostras, dict) or isinstance(refs, dict):
            linhas.append("")
            linhas.append("Amostras:")
            keys = []
            if isinstance(amostras, dict):
                keys.extend(amostras.keys())
            if isinstance(refs, dict):
                keys.extend(refs.keys())
            # ordena numericamente se possível
            def _key(k):
                try:
                    return (0, int(k))
                except (TypeError, ValueError):
                    return (1, str(k))
            for k in sorted(set(keys), key=_key):
                info = amostras.get(k, "—") if isinstance(amostras, dict) else "—"
                ref = refs.get(k, "—") if isinstance(refs, dict) else "—"
                marca = "  ◀ selecionada" if amostra_id is not None and str(k) == str(amostra_id) else ""
                linhas.append(f"  {k}: {info} | ref={ref}{marca}")
            usados.update({"amostras", "valores_referencia"})

        outros = [k for k in attrs if k not in usados]
        if outros:
            linhas.append("")
            linhas.append("Outros atributos:")
            for k in sorted(outros):
                v = attrs[k]
                if isinstance(v, (dict, list)):
                    v = json.dumps(v, ensure_ascii=False)
                linhas.append(f"  {k}: {v}")

        return "\n".join(linhas)

    def atualizar_metadados(self):
        """Exibe metadados do sensor/experimento (e contexto da amostra) ao selecionar na árvore."""
        items = self.tree.selectedItems()
        if not self.caminho_atual:
            self.meta_view.clear()
            return
        if not items:
            self.exibir_info_arquivo()
            return

        caminho = items[0].data(0, Qt.UserRole)
        if not caminho:
            self.exibir_info_arquivo()
            return

        try:
            with h5py.File(self.caminho_atual, "r") as h5_file:
                if caminho not in h5_file:
                    self.meta_view.setPlainText("Caminho não encontrado no arquivo.")
                    return

                obj = h5_file[caminho]
                blocos = []

                # Sobe até um grupo
                grupo = obj if isinstance(obj, h5py.Group) else obj.parent
                amostra_id = None

                # Dataset → grupo amostra
                if isinstance(obj, h5py.Dataset):
                    grupo = obj.parent
                    amostra_id = grupo.name.split("/")[-1]
                elif isinstance(grupo, h5py.Group):
                    tem_datasets = any(isinstance(c, h5py.Dataset) for c in grupo.values())
                    tem_attrs = len(grupo.attrs) > 0
                    if tem_datasets and not tem_attrs:
                        # grupo amostra sem attrs → metadados no experimento pai
                        amostra_id = grupo.name.split("/")[-1]
                        grupo = grupo.parent

                # Experimento (ou grupo com attrs)
                if isinstance(grupo, h5py.Group) and len(grupo.attrs) > 0:
                    titulo = "Experimento" if "identificador" in grupo.attrs or "amostras" in grupo.attrs else "Grupo"
                    if "sensor_id" in grupo.attrs or "nome" in grupo.attrs:
                        titulo = "Sensor"
                    blocos.append(self._texto_metadados_grupo(grupo, titulo, amostra_id=amostra_id))

                    # Se estamos num experimento, inclui também o sensor pai
                    pai = grupo.parent
                    if (
                        titulo == "Experimento"
                        and isinstance(pai, h5py.Group)
                        and pai.name != "/"
                        and len(pai.attrs) > 0
                    ):
                        blocos.append(self._texto_metadados_grupo(pai, "Sensor"))
                else:
                    blocos.append(f"[{grupo.name}]\n(sem metadados neste nível)")

                self.meta_view.setPlainText("\n\n".join(blocos))
        except Exception as e:
            self.meta_view.setPlainText(f"Erro ao ler metadados:\n{e}")

    def _caminhos_amostra_selecionados(self):
        """Retorna caminhos de grupos que contêm datasets (nível amostra)."""
        candidatos = []
        iterator = QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            item = iterator.value()
            if item.checkState(0) == Qt.Checked:
                caminho = item.data(0, Qt.UserRole)
                if caminho:
                    candidatos.append(caminho)
            iterator += 1

        if not candidatos:
            return []

        selecionados = []
        with h5py.File(self.caminho_atual, 'r') as h5_file:
            for caminho in candidatos:
                if caminho not in h5_file:
                    continue
                obj = h5_file[caminho]
                if isinstance(obj, h5py.Group) and any(
                    isinstance(child, h5py.Dataset) for child in obj.values()
                ):
                    selecionados.append(caminho)
        return selecionados

    def iniciar_analise(self):
        if not self.caminho_atual:
            QMessageBox.warning(self, "Aviso", "Abra um arquivo HDF5 primeiro.")
            return

        selecionados = self._caminhos_amostra_selecionados()
            
        if not selecionados:
            QMessageBox.warning(self, "Aviso", "Selecione pelo menos um grupo de Amostra.")
            return
            
        self.worker = DataWorker(self.caminho_atual, selecionados)
        self.worker.finished.connect(self.processamento_concluido)
        self.worker.error.connect(lambda msg: QMessageBox.critical(self, "Erro", msg))
        self.worker.start()

    def processamento_concluido(self, df):
        if df.empty:
            QMessageBox.warning(self, "Aviso", "O DataFrame gerado está vazio.")
            return
            
        self.df_bruto = df.copy()
        self.df_atual = df.copy()
        self.btn_tara.setEnabled(True)
        self._atualizar_tabela_e_eixos(preferir_rel=False)
        
        QMessageBox.information(self, "Sucesso", f"DataFrame carregado com {len(df)} registros e renderizado com sucesso!")

    def _atualizar_tabela_e_eixos(self, preferir_rel=False):
        """Atualiza tabela, comboboxes e gráfico a partir de df_atual."""
        df = self.df_atual
        if df is None or df.empty:
            return

        self.table.setRowCount(0)
        self.table.setRowCount(len(df))
        
        colunas_metadados = ['data', 'identificador', 'mensurando', 'amostra_id', 'valor_referencia', 'info_amostra']
        for i, row in df.iterrows():
            for j, col_name in enumerate(colunas_metadados):
                if col_name in df.columns:
                    val = str(row[col_name])
                    self.table.setItem(i, j, QTableWidgetItem(val))
                    
        colunas = list(df.columns)
        x_prev, y_prev, c_prev = self.cb_x.currentText(), self.cb_y.currentText(), self.cb_color.currentText()

        self.cb_x.blockSignals(True)
        self.cb_y.blockSignals(True)
        self.cb_color.blockSignals(True)
        
        self.cb_x.clear()
        self.cb_y.clear()
        self.cb_color.clear()
        
        self.cb_x.addItems(colunas)
        self.cb_y.addItems(colunas)
        self.cb_color.addItem("Nenhum")
        self.cb_color.addItems(colunas)

        # Defaults / preservação
        if preferir_rel and 'rel_resonant_wl_1' in colunas:
            self.cb_y.setCurrentText('rel_resonant_wl_1')
        elif y_prev in colunas:
            self.cb_y.setCurrentText(y_prev)
        elif 'resonant_wl_1' in colunas:
            self.cb_y.setCurrentText('resonant_wl_1')

        if x_prev in colunas:
            self.cb_x.setCurrentText(x_prev)
        elif 'valor_referencia' in colunas:
            self.cb_x.setCurrentText('valor_referencia')

        if c_prev in colunas or c_prev == "Nenhum":
            self.cb_color.setCurrentText(c_prev if c_prev else "Nenhum")
        elif 'identificador' in colunas:
            self.cb_color.setCurrentText('identificador')
            
        self.cb_x.blockSignals(False)
        self.cb_y.blockSignals(False)
        self.cb_color.blockSignals(False)
        
        self.atualizar_grafico()

    def abrir_dialogo_tara(self):
        if self.df_bruto is None or self.df_bruto.empty:
            QMessageBox.warning(self, "Aviso", "Processe dados antes de configurar a tara.")
            return

        dlg = TaraDialog(
            self.df_bruto,
            parent=self,
            protocolo_atual=self._tara_protocolo,
            filtro_agua=self._tara_filtro,
        )
        if dlg.exec_() != QDialog.Accepted:
            return

        cfg = dlg.configuracao()
        if cfg["remover"]:
            self.df_atual = remover_colunas_rel(self.df_bruto.copy())
            self._atualizar_tabela_e_eixos(preferir_rel=False)
            QMessageBox.information(self, "Tara", "Colunas rel_* removidas. Dados originais restaurados.")
            return

        if cfg["protocolo"] == "manual" and not cfg["amostras_manuais"]:
            QMessageBox.warning(self, "Aviso", "Selecione ao menos uma amostra de tara no protocolo manual.")
            return

        try:
            self.df_atual = aplicar_tara(
                self.df_bruto,
                protocolo=cfg["protocolo"],
                filtro_agua=cfg["filtro_agua"],
                amostras_manuais=cfg["amostras_manuais"],
            )
            self._tara_protocolo = cfg["protocolo"]
            self._tara_filtro = cfg["filtro_agua"]
            self._atualizar_tabela_e_eixos(preferir_rel=True)
            n_rel = sum(1 for c in self.df_atual.columns if str(c).startswith("rel_"))
            QMessageBox.information(
                self,
                "Tara aplicada",
                f"Protocolo: {PROTOCOLOS[cfg['protocolo']]}\n"
                f"{n_rel} colunas rel_* criadas. Selecione-as nos eixos para plotar.",
            )
        except Exception as e:
            QMessageBox.critical(self, "Erro na tara", str(e))

    def atualizar_grafico(self):
        """Função chamada sempre que o usuário altera os comboboxes ou o processamento termina"""
        if self.df_atual is None or self.df_atual.empty:
            return
            
        x_axis = self.cb_x.currentText()
        y_axis = self.cb_y.currentText()
        color_by = self.cb_color.currentText()
        tipo = self.cb_tipo.currentText()
        
        if not x_axis or not y_axis:
            return
            
        self.ax.clear()
        
        # Trata o caso de não colorir
        hue = None if color_by == "Nenhum" else color_by
        
        try:
            plot_kwargs = dict(data=self.df_atual, x=x_axis, y=y_axis, hue=hue, ax=self.ax)
            if tipo == "Dispersão":
                sns.scatterplot(**plot_kwargs)
            elif tipo == "Barras":
                sns.barplot(**plot_kwargs, errorbar="sd")
            else:
                sns.lineplot(**plot_kwargs, errorbar="sd", err_style="bars", marker='o')
            self.ax.set_title(f"{y_axis} vs {x_axis} ({tipo})")
        except Exception as e:
            self.ax.set_title(f"Aviso: Não foi possível plotar ({str(e)})")
            
        self.fig.tight_layout()
        self.canvas.draw()

    def alternar_tabela(self, visivel):
        """Exibe ou oculta a tabela abaixo do gráfico."""
        if visivel:
            self.table.show()
            self.right_splitter.setSizes(self._splitter_sizes_com_tabela)
        else:
            sizes = self.right_splitter.sizes()
            if sizes[1] > 0:
                self._splitter_sizes_com_tabela = sizes
            self.table.hide()
            total = sum(self.right_splitter.sizes()) or sum(self._splitter_sizes_com_tabela)
            self.right_splitter.setSizes([total, 0])

    def exportar_grafico(self):
        """Salva o gráfico atualmente exibido em arquivo de imagem."""
        if self.df_atual is None or self.df_atual.empty:
            QMessageBox.warning(self, "Aviso", "Não há gráfico para exportar. Processe dados primeiro.")
            return

        x_axis = self.cb_x.currentText() or "x"
        y_axis = self.cb_y.currentText() or "y"
        nome_sugerido = f"{y_axis}_vs_{x_axis}.png"

        file_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Exportar gráfico",
            nome_sugerido,
            "PNG (*.png);;PDF (*.pdf);;SVG (*.svg);;JPEG (*.jpg)",
        )
        if not file_path:
            return

        # Garante extensão se o usuário não digitou uma
        extensoes = {
            "PNG (*.png)": ".png",
            "PDF (*.pdf)": ".pdf",
            "SVG (*.svg)": ".svg",
            "JPEG (*.jpg)": ".jpg",
        }
        ext = extensoes.get(selected_filter, ".png")
        if not file_path.lower().endswith((".png", ".pdf", ".svg", ".jpg", ".jpeg")):
            file_path += ext

        try:
            self.fig.savefig(file_path, dpi=150, bbox_inches="tight")
            QMessageBox.information(self, "Sucesso", f"Gráfico salvo em:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Falha ao exportar o gráfico:\n{e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = H5Visualizer()
    win.show()
    sys.exit(app.exec_())