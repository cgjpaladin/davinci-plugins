# UIDispatcher

The UIDispatcher object has a few important functions to manage processing of events. The most important are:
## Functions
### AddWindow({properties}, [children])

**Description**

This function is creating a window element. 

**Type:** function: Accepts a dictionary of properties and a list of children, returns a Window object

```python
ui = fusion.UIManager
dispatcher = bmd.UIDispatcher(ui)

win = dispatcher.AddWindow({ 'ID': 'myWindow' }, [ ui.Label({ 'Text': 'Hello World!' }) ])
```

### AddDialog({properties}, [children])

**Description**

This function is

**Type:** function: Accepts a dictionary of properties and a list of children, returns a Dialog object

> **Note:** not tested yet
ui = fusion.UIManager
dispatcher = bmd.UIDispatcher(ui)
win = dispatcher.AddDialog({ 'ID': 'myDialog' }, [ ui.Label({ 'Text': 'Hello World!' }) ])

### RunLoop()

**Description**

This function runs a Loop listening to user events. 

**Type:** function: Call when your window is ready to receive user clicks and other events    return int

> **Note:** not tested yet
ui = fusion.UIManager
dispatcher = bmd.UIDispatcher(ui)
win = dispatcher.AddDialog({ 'ID': 'myDialog' }, [ ui.Label({ 'Text': 'Hello World!' }) ])
dispatcher.RunLoop()

### ExitLoop(int)

**Description**

This function exits the running loop. 

**Type:** function: Terminates the event processing, and returns int = any supplied exit code from RunLoop() 

> **Note:** not tested yet
dispatcher.ExitLoop(int)

Common usage is to create your window and set up any event handlers, including a Close handler for the window that calls ExitLoop(), 
then Show() your window and call RunLoop() to wait for user interaction:

```python
ui = fusion.UIManager
dispatcher = bmd.UIDispatcher(ui)

win = dispatcher.AddWindow({ 'ID': 'myWindow' }, [ ui.Label({ 'Text': 'Hello World!' }) ])

def OnClose(ev):
	dispatcher.ExitLoop()

win.On.myWindow.Close = OnClose

win.Show()
dispatcher.RunLoop()
```

AddWindow() will also accept a single child without needing a list, or a single dictionary containing both properties and child elements, for ease of use.

As well as constructing new child elements and layouts, the UIManager also offers a few useful functions:
## UIManager

### FindWindow(ID)

**Description**

This function returns the windows matching with ID

**Type:**  Returns an element with matching ID

```python
ui = fusion.UIManager
window = ui.FindWindow('win_id')
```

### FindWindows(ID)

**Description**

This function is

**Type:** Returns a list of all elements with matching ID

```python
ui = fusion.UIManager
windows = ui.FindWindows('win_id')
```

### QueueEvent(element, event, {info})

**Description**

This function is

**Type:** element= , event= , info= : Calls the element's event handler for 'event', passing it the dictionary 'info'

> **Note:** not tested yet
ui = fusion.UIManager
ui.QueueEvent(element, event, info)




