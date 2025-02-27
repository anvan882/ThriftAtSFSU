from flask import Flask, render_template

app = Flask(__name__)

@app.route("/")
def index():
    return render_template('index.html')
  
@app.route("/joe")
def joe():
    return render_template('joe.html', name="Joseph Shur") 

@app.route("/hilary")
def hilary():
    return render_template('hilary.html', name="Hilary Lui")

@app.route("/joseph")
def joseph():
    return render_template('about_JosephA.html', name="Joseph Alhambra")

@app.route("/annison")
def annison():
    return render_template('annison.html', name="Annison Van")

@app.route("/sid")
def sid():
    return render_template('sid.html', name="Sid Padmanabhuni")

if __name__ == '__main__':
    app.run()
