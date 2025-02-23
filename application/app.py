from flask import Flask, render_template

app = Flask(__name__)

@app.route("/")
def index():
    return render_template('index.html')
  
@app.route("/joe")
def joe():
    return render_template('joe.html') 

@app.route("/hilary")
def hilary():
    return render_template('hilary.html')

@app.route("/joseph")
def joseph():
    return render_template('about_JosephA.html')

@app.route("/annison")
def annison():
    return render_template('annison.html')

@app.route("/sid")
def sid():
    return render_template('sid.html')

if __name__ == '__main__':
    app.run()
