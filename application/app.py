from flask import Flask, render_template

app = Flask(__name__)

@app.route("/")
def index():
    return render_template('index.html')

@app.route("/joe")
def joe():
    return render_template('joe.html') 

if __name__ == '__main__':
    app.run()