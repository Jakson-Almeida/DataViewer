import sys
import h5py
import pandas as pd
import numpy as np
from PyQt5.QtWidgets import (QApplication, QMainWindow, QTreeWidget, QTreeWidgetItem, 
                             QHBoxLayout, QVBoxLayout, QPushButton, QWidget, QFileDialog, 
                             QTreeWidgetItemIterator, QMessageBox, QTableWidget, QTableWidgetItem, 
                             QSplitter, QComboBox, QLabel)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

# Importações do Matplotlib para embutir o gráfico no PyQt5
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import seaborn as sns
from dataframe_manager import hdf5_2_df

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
        
        # Árvore hierárquica em cima
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Estrutura do HDF5"])
        self.tree.itemChanged.connect(self.handle_item_changed)
        left_layout.addWidget(self.tree)
        
        # Botões embaixo e lado a lado (Layout Horizontal)
        buttons_layout = QHBoxLayout()
        self.btn_abrir = QPushButton("Abrir Arquivo .h5")
        self.btn_abrir.clicked.connect(self.abrir_arquivo)
        
        self.btn_analisar = QPushButton("Processar Selecionados")
        self.btn_analisar.clicked.connect(self.iniciar_analise)
        
        buttons_layout.addWidget(self.btn_abrir)
        buttons_layout.addWidget(self.btn_analisar)
        
        left_layout.addLayout(buttons_layout)
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
        right_splitter = QSplitter(Qt.Vertical)
        right_splitter.addWidget(self.canvas)
        right_splitter.addWidget(self.table)
        
        right_layout.addWidget(right_splitter)
        main_splitter.addWidget(right_container)
        
        # Ajuste de proporção inicial (Painel esquerdo: 1, Painel direito: 2)
        main_splitter.setSizes([400, 800])
        
        self.caminho_atual = None
        self.df_atual = None # Variável para guardar o dataframe para repintar o gráfico

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
            self.popular_tree(file_path)

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

    def iniciar_analise(self):
        if not self.caminho_atual:
            QMessageBox.warning(self, "Aviso", "Abra um arquivo HDF5 primeiro.")
            return

        selecionados = []
        iterator = QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            item = iterator.value()
            if item.checkState(0) == Qt.Checked:
                caminho = item.data(0, Qt.UserRole)
                # Amostra: /experimento/amostra (2 '/'); datasets têm 3
                if caminho and caminho.count('/') == 2:
                    selecionados.append(caminho)
            iterator += 1
            
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
            
        # Salva o DataFrame na classe para ser usado pela função de atualizar_grafico
        self.df_atual = df
            
        # 1. Atualizar a Tabela com metadados básicos
        self.table.setRowCount(0)
        self.table.setRowCount(len(df))
        
        colunas_metadados = ['data', 'identificador', 'mensurando', 'amostra_id', 'valor_referencia', 'info_amostra']
        for i, row in df.iterrows():
            for j, col_name in enumerate(colunas_metadados):
                if col_name in df.columns:
                    val = str(row[col_name])
                    self.table.setItem(i, j, QTableWidgetItem(val))
                    
        # 2. Configurar e popular os ComboBoxes com as colunas do DataFrame
        colunas = list(df.columns)
        
        # Bloqueia os sinais para não tentar plotar enquanto estamos preenchendo os dados
        self.cb_x.blockSignals(True)
        self.cb_y.blockSignals(True)
        self.cb_color.blockSignals(True)
        
        self.cb_x.clear()
        self.cb_y.clear()
        self.cb_color.clear()
        
        self.cb_x.addItems(colunas)
        self.cb_y.addItems(colunas)
        self.cb_color.addItem("Nenhum") # Adicionado o caso para não colorir
        self.cb_color.addItems(colunas)
        
        # Seta valores padrões se eles existirem no dataframe
        if 'valor_referencia' in colunas:
            self.cb_x.setCurrentText('valor_referencia')
        if 'resonant_wl_1' in colunas:
            self.cb_y.setCurrentText('resonant_wl_1')
        if 'identificador' in colunas:
            self.cb_color.setCurrentText('identificador')
            
        # Libera os sinais
        self.cb_x.blockSignals(False)
        self.cb_y.blockSignals(False)
        self.cb_color.blockSignals(False)
        
        # Pede para desenhar o gráfico com os valores que acabaram de ser selecionados
        self.atualizar_grafico()
        
        QMessageBox.information(self, "Sucesso", f"DataFrame carregado com {len(df)} registros e renderizado com sucesso!")

    def atualizar_grafico(self):
        """Função chamada sempre que o usuário altera os comboboxes ou o processamento termina"""
        if self.df_atual is None or self.df_atual.empty:
            return
            
        x_axis = self.cb_x.currentText()
        y_axis = self.cb_y.currentText()
        color_by = self.cb_color.currentText()
        
        if not x_axis or not y_axis:
            return
            
        self.ax.clear()
        
        # Trata o caso de não colorir
        hue = None if color_by == "Nenhum" else color_by
        
        try:
            sns.lineplot(data=self.df_atual, x=x_axis, y=y_axis, hue=hue, 
                         errorbar="sd", err_style="bars", marker='o', ax=self.ax)
            self.ax.set_title(f"{y_axis} vs {x_axis}")
        except Exception as e:
            self.ax.set_title(f"Aviso: Não foi possível plotar ({str(e)})")
            
        self.fig.tight_layout()
        self.canvas.draw()

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