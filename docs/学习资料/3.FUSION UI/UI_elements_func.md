# Functions

Most elements have functions that can be called from them as well:

* Show()
* Hide()
* Raise()
* Lower()
* Close()            Returns boolean
* Find(ID)            Returns child element with matching ID
* GetChildren()        Returns list
* AddChild(element)
* RemoveChild(element)
* SetParent(element)
* Move(point)
* Resize(size)
* Size()            Returns size
* Pos()                Returns position
* HasFocus()        Returns boolean
* SetFocus(reason)    Accepts string "MouseFocusReason", "TabFocusReason", "ActiveWindowFocusReason", "OtherFocusreason", etc
* FocusWidget()        Returns element
* IsActiveWindow()    Returns boolean
* SetTabOrder(element)
* Update()
* Repaint()
* SetPaletteColor(r,g,b)
* QueueEvent(name, info)  Accepts event name string and dictionary of event attributes
* GetItems()            Returns dictionary of all child elements

Some elements have extra functions of their own:

## Label

### SetSelection(int, int)

**Description**

This function used to

**Type:** int= int=

> **Note:** Not tested yet
> win['mylabel'].SetSelection(0,1)

### HasSelection()

**Description**

This function return True if Label has selection

**Type:** return bool

> **Note:** Not tested yet
> win['mylabel'].HasSelection()

### SelectedText()

**Description**

This function return SelectedText string

**Type:** return string

> **Note:** Not tested yet
> win['mylabel'].SelectedText()

### SelectionStart()

**Description**

This function return the index of the selection

**Type:** return int

> **Note:** Not tested yet
> win['mylabel'].SelectionStart()

## Button

### Click()

**Description**

This function is

**Type:** func

> **Note:** Not tested yet
> win['mybutton'].Click()

### Toggle()

**Description**

This function is

**Type:** func

> **Note:** Not tested yet
> win['mybutton'].Toggle()

### AnimateClick()

**Description**

This function is

**Type:** func

> **Note:** Not tested yet
> win['mybutton'].AnimateClick()

## CheckBox

### Click()

**Description**

This function is

**Type:** func

> **Note:** Not tested yet
> win['mycheckbox'].Click()

### Toggle()

**Description**

This function is

**Type:** func

> **Note:** Not tested yet
> win['mycheckbox'].Toggle()

### AnimateClick()

**Description**

This function is

**Type:** func

> **Note:** Not tested yet
> win['mycheckbox'].AnimateClick()

## ComboBox

### AddItem(string)

**Description**

This function add the item to the ComboBox list.

**Type:** func

```python
win.Find('combo_1').AddItem('Item Name')

```

### InsertItem(int, string)

**Description**

This function is inserting an item at the specified index.

**Type:** func

```python
win.Find('combo_1').InsertItem(1, 'New item')

```

### AddItems(list)

**Description**

This function is adding a list of item to the ComboBox list.

**Type:** func

```python
win.Find('combo_1').AddItems(['Item 1', 'Item 2', 'Item 3'])

```

### InsertItems(int, list)

**Description**

This function is inserting a list of items at the specified index.

**Type:** int= index, list=[string]

```python
win.Find('combo_1').InsertItems(1, ['Item 1', 'Item 2'])

```

### InsertSeparator(int)

**Description**

This function inserts a Seprator in the list at the specified index.

**Type:** int= index

```python
win.Find('combo_1').InsertSeparator(2)  #insert after second item

```

### RemoveItem(int)

**Description**

This function is

**Type:** int= index

```python
win.Find('combo_1').RemoveItem(2)  #remove third item

```

### Clear()

**Description**

This function removes all item from the ComboBox list

**Type:** func

```python
win.Find('combo_1').Clear()

```

### SetEditText(string)

**Description**

This function sets the Text to appear in the editable Combox Item. 

`ComboBox must be Editable`

**Type:** func

```python
ui.ComboBox({'ID':'combo_1', 'Editable': True }),

win.Find('combo_1').SetEditText('My text')

```

### ClearEditText()

**Description**

This function clears the EditText box in the Combox Item. 

`ComboBox must be Editable`

**Type:** func

```python
ui.ComboBox({'ID':'combo_1', 'Editable': True }),

win.Find('combo_1').ClearEditText()

```

### Count()

**Description**

This function returns the number of item in the ComboBox list.

**Type:** func

```python
ui.ComboBox({'ID':'combo_1'}),
win.Find("combo_1").AddItems(["Item 1","Item 2","Item 3"])
item_count = win.Find('combo_1').Count()
print(item_count)  # 3

```

### ShowPopup()

**Description**

This function opens the ComboBox list to display content

**Type:** func

```python
win.Find('combo_1').ShowPopup()

```

### HidePopup()

**Description**

This function closes the ComboBox list to hide content

**Type:** func

```python
win.Find('combo_1').HidePopup()

```

## SpinBox

### SetRange(int, int)

**Description**

This function is setting a Minimum and Maximum value to the SpinBox.

**Type:** func

```python
win.Find('spinbox_1').SetRange(0, 4)  #min=0, max=4

```

### StepBy(int)

**Description**

This function adding the specified value to the SpinBox.

**Type:** func

```python
win.Find('spinbox_1').StepBy(2)  #adds 2

```

### StepUp()

**Description**

This function is adding the current Step value to the SpinBox (default=1)

**Type:** func

```python
win.Find('spinbox_1').StepUp()

```

### StepDown()

**Description**

This function is removing the current Step value to the SpinBox (default=1)

**Type:** func

```python
win['myspinbox'].StepDown()

```

### SelectAll()

**Description**

This function is selecting all the numbers in the SpinBox

**Type:** func

```python
win.Find('spinbox_1').SelectAll()

```

### Clear()

**Description**

This function clears the SpinBox display

**Type:** func

```python
win.Find('spinbox_1').Clear()

```

## Slider

### SetRange(int, int)

**Description**

This function is setting a Minimum and Maximum value to the Slider.

**Type:** func

```python
win.Find('slider_1').SetRange(0, 4)  #min=0, max=4

```

### TriggerAction(string)

**Description**

This function is

**Type:** func

> **Note:** Not tested yet
> win['myslider'].TriggerAction(string)

## LineEdit

### SetSelection(int, int)

**Description**

This function is selecting a range of characters in the LineEdit.

**Type:** func int = index start, index end

```python
win.Find('le_1').SetSelection(0, 4)  #selects the first 4 characters

```

### HasSelectedText()

**Description**

This function is

**Type:** return bool

> **Note:** Not tested yet
> win['le_1'].HasSelectedText()

### SelectedText()

**Description**

This function is

**Type:** return string

> **Note:** Not tested yet
> win['le_1'].SelectedText()

### SelectionStart()

**Description**

This function is

**Type:** return int

> **Note:** Not tested yet
> win['le_1'].SelectionStart()

### SelectAll()

**Description**

This function is selecting all the text in the LineEdit element.

**Type:** 

```python
win.Find('le_1').SelectAll()

```

### Clear()

**Description**

This function deletes all the text in the LineEdit element.

**Type:** return 

```python
win.Find('le_1').Clear()

```

### Cut()

**Description**

This function will copy to clipboard and remove the selected LineEdit characters. 
`A selection in the LineEdit is required`

**Type:** 

```python
win.Find('le_1').SetSelection(0, 4)
win.Find('le_1').Cut()  #this will cut the first 4 characters

```

### Copy()

**Description**

This function will copy to clipboard the selected LineEdit characters.
`A selection in the LineEdit is required`

**Type:** return

```python
win.Find('le_1').SetSelection(0, 4)
win.Find('le_1').Copy()  #this will copy the first 4 characters

```

### Paste()

**Description**

This function paste the clipboard content to the LineEdit element.

**Type:** 

```python
win.Find('le_1').Paste()

```

### Undo()

**Description**

This function wil undo the last action made in the TextEdit element.

**Type:** 

```python
win.Find('le_1').Undo()

```

### Redo()

**Description**

This function is

**Type:** 

> **Note:** Not tested yet
> win['le_1'].Redo()

### Deselect()

**Description**

This function will deselect the selected text of the LineEdit element.

**Type:** 

```python
win.Find('le_1').Deselect()

```

### Insert(string)

**Description**

This function insert the text string at the cursor position in the LineEdit element.

**Type:** 

```python
win.Find('le_1').Insert('New Text')

```

### Backspace()

**Description**

This function remove the last character from the cursor position in the LineEdit element.

**Type:** 

```python
win.Find('le_1').Backspace()

```

### Del()

**Description**

This function remove the next character from the cursor position in the LineEdit element.

**Type:** 

```python
win.Find('le_1').Del()

```

### Home(bool)

**Description**

This function is selecting all characters from cursor to beginning when set to True.

**Type:** 

```python
win.Find('le_1').Home(True)

```

### End(bool)

**Description**

This function is selecting all characters from cursor to end when set to True.

**Type:** 

```python
win.Find('le_1').End(True)

```

### CursorPositionAt(point)

**Description**

This function is

**Type:** return int

> **Note:** Not tested yet
> win['le_1'].CursorPositionAt(point)

## TextEdit

### InsertPlainText(string)

**Description**

This function insert the text string at the cursor position in the TextEdit element.

**Type:** func 

```python
win.Find('te_1').InsertPlainText('New text')

```

### InsertHTML(string)

**Description**

This function insert the HTML code string at the cursor position in the TextEdit element.

**Type:** func 

```python
win.Find('te_1').InsertHTML('<h1>My title</h1>')

```

### Append(string)

**Description**

This function is adding the string on the next line of the TextEdit box.

**Type:** func 

```python
win.Find('te_1').Append('My text')

```

### SelectAll()

**Description**

This function is selecting all the text in the TextEdit element.

**Type:** func 

```python
win.Find('te_1').SelectAll()

```

### Clear()

**Description**

This function deletes all the text in the LineEdit element.

**Type:** func 

```python
win.Find('te_1').Clear()

```

### Cut()

**Description**

This function will copy to clipboard and remove the selected LineEdit characters. 
`A selection in the LineEdit is required`

**Type:** 

```python
win.Find('te_1').SetSelection(0, 4)
win.Find('te_1').Cut()  #this will cut the first 4 characters

```

### Copy()

**Description**

This function will copy to clipboard the selected characters.
`A selection in the TextEdit is required`

**Type:** return

```python
win.Find('te_1').SelectAll()
win.Find('te_1').Copy()  #this will copy all text to clipbboard

```

### Paste()

**Description**

This function paste the clipboard content to the cursor position in the TextEdit element.

**Type:** 

```python
win.Find('te_1').Paste()

```

### Undo()

**Description**

This function wil undo the last action made on each line of the TextEdit element.

**Type:** 

```python
win.Find('te_1').Undo()

```

### Redo()

**Description**

This function is

**Type:** 

> **Note:** Not tested yet
> win['te_1'].Redo()

### ScrollToAnchor(string)

**Description**

This function is

**Type:** func 

> **Note:** Not tested yet
> win['te_1'].ScrollToAnchor('My text')

### ZoomIn(int)

**Description**

This function is increase the displayed text size by defined number.

**Type:** func 

```python
win.Find('te_1').ZoomIn(14)  #will display text with 14pt size

```

### ZoomOut(int)

**Description**

This function is decrease the displayed text size by defined number.

**Type:** func 

> **Note:** Not tested yet
> win.Find('te_1').ZoomOut(2)  #will reduce text size of 2pt

### EnsureCursorVisible()

**Description**

This function is

**Type:** func 

> **Note:** Not tested yet
> win['te_1'].EnsureCursorVisible()

### MoveCursor(moveOperation, moveMode)

**Description**

This function is

**Type:** moveOperation = , moveMode =

> **Note:** Not tested yet
> win['te_1'].MoveCursor(moveOperation, moveMode)

### CanPaste()

**Description**

This function is

**Type:** return bool 

> **Note:** Not tested yet
> win['te_1'].CanPaste()

### AnchorAt(point)

**Description**

This function is

**Type:** return string 

> **Note:** Not tested yet
> win['te_1'].AnchorAt(point)

### Find(string, findFlags)

**Description**

This function is

**Type:** string= , findFlags= : return bool 

> **Note:** Not tested yet
> win['te_1'].Find('my text', findFlags)

## TabBar

### AddTab(string)

**Description**

This function adds a Tab with specified name to the TabBar

**Type:** string

```python
win.Find('tabbar_1').AddTab('Tab 1')

```

### InsertTab(int, string)

**Description**

This function insert a Tab in the TabBar at specified index.

**Type:** returns tab index (int)

```python
win.Find('tabbar_1').InsertTab(0, 'Tab 0')  #insert tab at index 0

```

### Count()

**Description**

This function counts the number of Tabs

**Type:** return number of Tab 

```python
print(win.Find('tabbar_1').Count())

```

### RemoveTab(int)

**Description**

This function is

**Type:** int= Tab index 

```python
win.Find('tabbar_1').RemoveTab(0)  #remove first tab

```

### MoveTab(int, int)

**Description**

This function moves a Tab to another position

**Type:** int=tab index to move  int=tab index destination 

```python
win.Find('tabbar_1').MoveTab(1, 0)  #move second tab to first position

```

## Tree

### AddTopLevelItem(item)

**Description**

This function adds the item at the top of the Tree.

**Type:** item= TreeItem

```python
item = win.Find('tree_1').NewItem()
item.Text[0] = 'My Text'
win.Find('tree_1').AddTopLevelItem(item)

```

### InsertTopLevelItem(int, item)

**Description**

This function insert the item at specified position.

**Type:** int= index, item= TreeItem  

```python
item = win.Find('tree_1').NewItem()
item.Text[0] = 'Insert'
win.Find('tree_1').InsertTopLevelItem(0, item)

```

### SetHeaderLabel(string)

**Description**

This function is setting the name for the first header

**Type:** string= header label

```python
win.Find('tree_1').SetHeaderLabel('New header')

```

### CurrentColumn()

**Description**

This function returns the selected column index.

**Type:** returns int

```python
print(win.Find('tree_1').CurrentColumn())

```

### SortColumn()

**Description**

This function is

**Type:** return int

> **Note:** Not tested yet
> win['mytree'].SortColumn()

### TopLevelItemCount()

**Description**

This function return the number of Item in the Tree. (row)

**Type:** returns

```python
print(win.Find('tree_1').TopLevelItemCount())

```

### CurrentItem()

**Description**

This function returns the selected Item in the Tree (row)

**Type:** return the UITreeItem

```python
print(win.Find('tree_1').CurrentItem().Text[0])  #print first column Text of the selected TreeItem (row)

```

### TopLevelItem(int)

**Description**

This function return the UITreeItem at the specified index. (row)

**Type:** int= index 

```python
print(win.Find('tree_1').TopLevelItem(1).Text[0])  #will print the Text of the second Item (row), first column

```

### TakeTopLevelItem(int)

**Description**

This function removes and returns the UITreeItem at the specified index. (row)

**Type:** int=   return item

```python
win.Find('tree_1').TakeTopLevelItem(1)

```

### InvisibleRootItem()

**Description**

This function is

**Type:** return item

> **Note:** Not tested yet
> win['mytree'].InvisibleRootItem()

### HeaderItem()

**Description**

This function is

**Type:** return item

> **Note:** Not tested yet
> win['mytree'].HeaderItem()

### IndexOfTopLevelItem(item)

**Description**

This function returns the index of the specified UITreeItem.

**Type:** return int

```python
some_item = win.Find('tree_1').TopLevelItem(1)
print(win.Find('tree_1').IndexOfTopLevelItem(some_item))  #print 1

```

### ItemAbove(item)

**Description**

This function returns the UITreeItem above the specified UITreeItem.

**Type:** item= UITreeItem   returns UITreeItem

```python
some_item = win.Find('tree_1').TopLevelItem(1)
item_above = win.Find('tree_1').ItemAbove(some_item)  #item_above is UITreeItem at index 0

```

### ItemBelow(item)

**Description**

This function is

**Type:** item= UITreeItem   returns UITreeItem

```python
some_item = win.Find('tree_1').TopLevelItem(0)
item_below = win.Find('tree_1').ItemBelow(some_item)  #item_below is UITreeItem at index 1

```

### ItemAt(point)

**Description**

This function is

**Type:** point=    return item

> **Note:** Not tested yet
> win['mytree'].ItemAt(point)

### Clear()

**Description**

This function empty all data from the Tree.

**Type:** 

```python
win.Find('tree_1').Clear()

```

### VisualItemRect(item)

**Description**

This function returns the rectangle on the viewport occupied by the item

**Type:** returns {int x, int y, int width, int height}

```python
some_item = win.Find('tree_1').TopLevelItem(1)
print(win.Find('tree_1').VisualItemRect(some_item))   #print {1: 20, 2: 20, 3: 208, 4: 20}

```

### SetHeaderLabels(list)

**Description**

This function sets the labels header for multiple columns

**Type:** list of string

```python
win.Find('tree_1').SetHeaderLabels(['header1', 'header2'])

```

### SetHeaderItem(item)

**Description**

This function is

**Type:** item = 

> **Note:** Not tested yet
> win['mytree'].SetHeaderItem(item)

### InsertTopLevelItems(int, list)

**Description**

This function inserts a list of UITreeItems from a list at the specified index.

**Type:** int= index to insert items, list = list of UITreeItems

```python
item1 = win.Find('tree_1').NewItem()
item1.Text[0] = 'name1'
item2 = win.Find('tree_1').NewItem()
item2.Text[0] = 'name2'
win.Find('tree_1').InsertTopLevelItems(0, [item1, item2])  #insert items at index 0

```

### AddTopLevelItems(list)

**Description**

This function adds the list of TreeItems at the end of the Tree.

**Type:** list = list of TreeItem

```python
item1 = win.Find('tree_1').NewItem()
item1.Text[0] = 'name1'
item2 = win.Find('tree_1').NewItem()
item2.Text[0] = 'name2'
win.Find('tree_1').AddTopLevelItems([item1, item2])

```

### SelectedItems()

**Description**

This function is

**Type:** return list of all selected UITreeItems

> **Note:** Not tested yet
> win['mytree'].SelectedItems()

### FindItems(string, flags, column)

**Description**

This function searches for a string with a dictionary or conditions in a specified column index.

flags:

* 'MatchExactly' : bool
* 'MatchFixedString' : bool
* 'MatchContains' : bool
* 'MatchStartsWith' : bool
* 'MatchEndsWith' : bool
* 'MatchCaseSensitive' : bool
* 'MatchRegExp' : bool
* 'MatchWildcard' : bool
* 'MatchWrap' : bool
* 'MatchRecursive' : bool

**Type:** string= text to find , flags= dict, column = int  Returns list of UITreeItems

```python
found_item = win.Find('tree_1').FindItems("*",
{
    'MatchExactly' : False,
    'MatchFixedString' : False,
    'MatchContains' : False,
    'MatchStartsWith' : False,
    'MatchEndsWith' : False,
    'MatchCaseSensitive' : False,
    'MatchRegExp' : False,
    'MatchWildcard' : True,
    'MatchWrap' : False,
    'MatchRecursive' :True,
}, 0)
# print all items of column 0 matching conditions, * is used as a wildcard

```

### SortItems(int, string)

**Description**

This function is sorting the TreeItems of the specified column index based on the specified ordering.  

`Check out the qt5 documentation for more details <https://doc.qt.io/qt-5/qtreewidget.html#sortItems>`_

order:

* 'AscendingOrder' : The items are sorted ascending e.g. starts with 'AAA' ends with 'ZZZ' in Latin-1 locales
* 'DescendingOrder' : The items are sorted descending e.g. starts with 'ZZZ' ends with 'AAA' in Latin-1 locales

`Check out the qt5 documentation for more details <https://doc.qt.io/qt-5/qt.html#SortOrder-enum>`_

**Type:** int= column index, string= sorting option

```python
win.Find('tree_1').SortItems(0, 'AscendingOrder')

```

### ScrollToItem(item)

**Description**

This function is

**Type:** item=

> **Note:** Not tested yet
> win['mytree'].ScrollToItem(item)

### ResetIndentation()

**Description**

This function is

**Type:** func

> **Note:** Not tested yet
> win['mytree'].ResetIndentation()

### SortByColumn(int, string)

**Description**

This function Sorts the model by the values in the given column and order.

`Check out the qt5 documentatatoin for more details <https://doc.qt.io/qt-5/qtreeview.html#sortByColumn>`_

order:

* 'AscendingOrder' : The items are sorted ascending e.g. starts with 'AAA' ends with 'ZZZ' in Latin-1 locales
* 'DescendingOrder' : The items are sorted descending e.g. starts with 'ZZZ' ends with 'AAA' in Latin-1 locales

**Type:** int= column index, string= order 

```python
win.Find('tree_1').SortByColumn(0, 'AscendingOrder')

```

### FrameWidth()

**Description**

This function is

**Type:** return int

> **Note:** Not tested yet
> win['mytree'].FrameWidth()

## TreeItem

### AddChild(item)

**Description**

This function is adding an item as a child to an existing TreeItem.

**Type:** func

```python
itm = win.Find('my_tree').NewItem()
itm.Text[0] = "First cell"
itm2 = win.Find('my_tree').NewItem()
itm2.Text[0] = "Child of itm"

win.Find('my_tree').AddTopLevelItem(itm)

itm.AddChild(itm2)

```

### InsertChild(int, item)

**Description**

This function is inserting an item as a child to an existing TreeItem to a specified index.

**Type:** func

```python
parent = win.Find('tree_1').NewItem()
parent.Text[0] = 'Text A'
child = win.Find('tree_1').NewItem()
child.Text[0] = 'Text B'
win.Find('tree_1').AddTopLevelItem(parent)

parent.InsertChild(0, child)

```

### RemoveChild(item)

**Description**

This function remove the child of the UITreeItem.

**Type:** func

```python
parent.RemoveChild(child)        

```

### SortChildren(int, order)

**Description**

This function is sorting the Child of UITreeItem of the specified column index based on the specified ordering.

order:

* 'AscendingOrder' : The items are sorted ascending e.g. starts with 'AAA' ends with 'ZZZ' in Latin-1 locales
* 'DescendingOrder' : The items are sorted descending e.g. starts with 'ZZZ' ends with 'AAA' in Latin-1 locales

**Type:** int= column index, string= order 

```python
parent.SortChildren(0, 'AscendingOrder')

```

### InsertChildren(int, list)

**Description**

This function inserts a list of UITreeItem as child of a parent UITreeItem at specified index.

**Type:** int= , list= 

```python
parent.InsertChildren(0, [child, child2]) 

```

### AddChildren(list)

**Description**

This function adds a list of UITreeItem as child of a parent UITreeItem.

**Type:** list= [UITreeItem, ...]

```python
parent.AddChildren([child, child2])

```

### IndexOfChild(item)

**Description**

This function returns the index of the specified UITreeItem child.

**Type:** return int

```python
print(parent.IndexOfChild(child2))  #print 1 for second child

```

### Clone()

**Description**

This function is

**Type:** return item

> **Note:** Not tested yet
> win['mytreeitem'].Clone()

### TreeWidget()

**Description**

This function is

**Type:** return tree

> **Note:** Not tested yet
> win['mytreeitem'].TreeWidget()

### Parent()

**Description**

This function returns the UITreeItem parent of the specified UITreeItem child.

**Type:** return item

```python
print(child.Parent())

```

### Child(int)

**Description**

This function returns the UITreeItem child at specified index of the UITreeItem parent.

**Type:** int=   return item

```python
print(parent.Child(0))  #the UITreeItem child at index 0

```

### TakeChild(int)

**Description**

This function removes and returns the child UITreeItem at specified index.

**Type:** int=index   return item

```python
removed_child = parent.TakeChild(0)

```

### ChildCount()

**Description**

This function returns the child count of the parent UITreeItem.

**Type:** return int

```python
print(parent.ChildCount())

```

### ColumnCount()

**Description**

This function returns the number of column of a UITreeItem containing data.

**Type:** return int

```python
print(parent.ColumnCount())

```

## Window

### Show()

**Description**

This function is showing the window to the user.

**Type:** func

```python
win.Show()

```

### Hide()

**Description**

This function is hiding the window.

**Type:** func

```python
win.Hide()

```

### RecalcLayout()

**Description**

This function is

**Type:** func

> **Note:** Not tested yet
> win.RecalcLayout()

## Dialog

### Exec()

**Description**

This function is

**Type:** func

> **Note:** Not tested yet
> dialog.Exec()

### IsRunning()

**Description**

This function is

**Type:** func

> **Note:** Not tested yet
> dialog.IsRunning()

### Done()

**Description**

This function is

**Type:** func

> **Note:** Not tested yet
> dialog.Done()

### RecalcLayout()

**Description**

This function is

**Type:** func

> **Note:** Not tested yet
> dialog.RecalcLayout()

Elements can be accessed by the window's FindWindow(id) function, or by assigning them to a variable for later usage, which is more efficient. 
The GetItems() function will return a dictionary of all child elements for ease of access.

```python
win_itms = win.GetItems()
win_itms['ElementID'].func()

```

## Timer

### Start()

**Description**

This function starts the Timer element.

**Type:** func

> **Note:** Not tested yet
> ui.Timer({ 'ID': 'MyTimer', 'Interval': 1000 })  # 1000 millisecs

### Stop()

**Description**

This function stops the Timer element.

**Type:** func

> **Note:** Not tested yet
> MyTimer.Stop()
