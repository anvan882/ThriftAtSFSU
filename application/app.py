from flask import Flask, render_template

app = Flask(__name__)

@app.route("/")
def index():
    return render_template('index.html')



@app.route("/hilary")
def hilary():
    return render_template('hilary.html')

if __name__ == '__main__':
    app.run()