from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt


class RowModel(QAbstractListModel):
    RowRole = Qt.UserRole + 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []

    def roleNames(self): return {self.RowRole: b'row'}
    def rowCount(self, parent=QModelIndex()): return 0 if parent.isValid() else len(self.rows)
    def data(self, index, role=Qt.DisplayRole):
        if role == self.RowRole and index.isValid() and index.row() < len(self.rows): return self.rows[index.row()]
        return None

    def update(self, rows):
        if not rows:
            if self.rows:
                self.beginRemoveRows(QModelIndex(),0,len(self.rows)-1);self.rows=[];self.endRemoveRows()
            return
        if not self.rows:
            self.beginInsertRows(QModelIndex(),0,len(rows)-1);self.rows=list(rows);self.endInsertRows()
            return
        wanted={r['id'] for r in rows}
        for index in range(len(self.rows)-1,-1,-1):
            if self.rows[index]['id'] not in wanted:
                self.beginRemoveRows(QModelIndex(),index,index);self.rows.pop(index);self.endRemoveRows()
        for index,row in enumerate(rows):
            if index<len(self.rows) and self.rows[index]['id']==row['id']:
                self.rows[index]=row
                continue
            source=next((i for i in range(index,len(self.rows)) if self.rows[i]['id']==row['id']),None)
            if source is None:
                self.beginInsertRows(QModelIndex(),index,index);self.rows.insert(index,row);self.endInsertRows()
            else:
                self.beginMoveRows(QModelIndex(),source,source,QModelIndex(),index)
                self.rows.insert(index,self.rows.pop(source));self.rows[index]=row;self.endMoveRows()
        self.dataChanged.emit(self.index(0),self.index(len(rows)-1),[self.RowRole])
