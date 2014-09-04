# -*- coding: utf-8 -*-
"""
/***************************************************************************
 GIS.lab Web plugin
 Publish your projects into GIS.lab Web application
 ***************************************************************************/
"""

# Import the PyQt and QGIS libraries
from qgis.core import *
from PyQt4.QtGui import *
from PyQt4.QtCore import *


def _save_topic(dialog, topic_item):
	visible_overlays = []
	def collect_visible_overlays(widget):
		if widget.data(0, Qt.UserRole):
			#if not widget.isHidden() and widget.checkState(0) == Qt.Checked:
			if not widget.isDisabled() and widget.checkState(0) == Qt.Checked:
				visible_overlays.append(widget.text(0))
		else:
			for index in range(widget.childCount()):
				collect_visible_overlays(widget.child(index))
	collect_visible_overlays(dialog.topicLayers.invisibleRootItem())
	topic_item.setData(Qt.UserRole, {
		'abstract': dialog.topicAbstract.toPlainText(),
		'visible_overlays': visible_overlays
	})

def setup_topics_ui(dialog, overlay_layers_tree):
	def add_topic():
		item = QListWidgetItem("New topic")
		item.setFlags(item.flags() | Qt.ItemIsEditable)
		dialog.topicsList.addItem(item)
		dialog.topicsList.editItem(item)
		dialog.topicsList.setCurrentRow(dialog.topicsList.count()-1)

	def remove_topic():
		dialog.topicsList.takeItem(dialog.topicsList.row(dialog.topicsList.selectedItems()[0]))

	dialog.addTopic.released.connect(add_topic)
	dialog.removeTopic.released.connect(remove_topic)

	def copy_tree_widget(widget):
		new_widget = QTreeWidgetItem()
		new_widget.setText(0, widget.text(0))
		new_widget.setData(0, Qt.UserRole, widget.data(0, Qt.UserRole))
		new_widget.setFlags(widget.flags())
		is_hidden = widget.checkState(1) == Qt.Checked
		if is_hidden:
			new_widget.setDisabled(True)
		for index in range(widget.childCount()):
			child = widget.child(index)
			new_widget.addChild(copy_tree_widget(child))
		new_widget.setCheckState(0, Qt.Checked)
		return new_widget

	dialog.topicLayers.addTopLevelItems(copy_tree_widget(dialog.overlaysTree.invisibleRootItem()).takeChildren())

	# hide excluded layer items, must be done after attaching of all widgets to the QTreeWidget
	def hide_excluded_layers(widget):
		for index in range(widget.childCount()):
			hide_excluded_layers(widget.child(index))
		if widget.checkState(0) == Qt.Unchecked:
			for topic_layer_item in dialog.topicLayers.findItems(widget.text(0), Qt.MatchExactly | Qt.MatchRecursive):
				topic_layer_item.setHidden(True)
	hide_excluded_layers(dialog.overlaysTree.invisibleRootItem())

	# setup synchronization of available and hidden layers in topics with with main layers tree widget
	def itemchanged(item, column):
		# layer visibility changed
		topic_layer_item = dialog.topicLayers.findItems(item.text(0), Qt.MatchExactly | Qt.MatchRecursive)[0]
		if column == 0:
			topic_layer_item.setHidden(item.checkState(0) == Qt.Unchecked)
			# this helps to avoid empty layers group to be visible in topics
			if item.parent() and item.parent().checkState(0) == Qt.Unchecked:
				topic_layer_item.parent().setHidden(True)
		elif column == 1:
			is_hidden = item.checkState(1) == Qt.Checked
			topic_layer_item.setDisabled(is_hidden)

	dialog.overlaysTree.itemChanged.connect(itemchanged)

	dialog.topicWidget.setEnabled(False)

	def topic_changed(current, previous):
		if previous is None:
			dialog.topicWidget.setEnabled(True)
		else:
			_save_topic(dialog, previous)
		if current:
			# load topic data to UI
			current_data = current.data(Qt.UserRole) or {}
			dialog.topicAbstract.setPlainText(current_data.get('abstract', ''))
			visible_overlays = current_data.get('visible_overlays')
			def set_visible_overlays(widget):
				if widget.data(0, Qt.UserRole):
					if not widget.isDisabled():
						if visible_overlays:
							widget.setCheckState(0, Qt.Checked if widget.text(0) in visible_overlays else Qt.Unchecked)
						else:
							widget.setCheckState(0, Qt.Checked)
				else:
					for index in range(widget.childCount()):
						set_visible_overlays(widget.child(index))
			set_visible_overlays(dialog.topicLayers.invisibleRootItem())

	dialog.topicsList.currentItemChanged.connect(topic_changed)

def load_topics_from_metadata(dialog, metadata):
	"""load topics from previous version of published project"""
	for topic_data in metadata.get('topics') or []:
		item = QListWidgetItem(topic_data.pop('title'))
		item.setFlags(item.flags() | Qt.ItemIsEditable)
		item.setData(Qt.UserRole, topic_data)
		dialog.topicsList.addItem(item)
	dialog.topicsList.setCurrentRow(0)

def get_topics(dialog):
	"""Returns list of topics data (title, abstract, visible layers)"""
	if dialog.topicsList.selectedItems():
		_save_topic(dialog, dialog.topicsList.selectedItems()[0])
	topics = []
	for index in range(dialog.topicsList.count()):
		item = dialog.topicsList.item(index)
		topic_data = dict(item.data(Qt.UserRole))
		topic_data['title'] = item.text()
		topics.append(topic_data)
	return topics