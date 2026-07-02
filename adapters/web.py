@app.post("/event")
def event(req):
    return adapter.handle(req.input, "web")
