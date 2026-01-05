# Import the libraries we need
from flask import Flask, render_template_string, request, redirect, url_for
import pandas as pd
import sqlite3
import os
from datetime import datetime

# Create the Flask app
app = Flask(__name__)
app.secret_key = 'my-secret-key-12345'  # Change this to any random string

# Create a folder to temporarily store uploaded files
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# ===== DATABASE SETUP =====
def setup_database():
    """Create the database and table if they don't exist"""
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY,
            date TEXT,
            description TEXT,
            amount REAL,
            category TEXT
        )
    ''')
    conn.commit()
    conn.close()

# ===== CATEGORIZATION LOGIC =====
def categorize_transaction(description, amount):
    """Figure out what category a transaction belongs to"""
    description = description.lower()
    
    # If it's positive, it's income
    if amount > 0:
        return 'Income'
    
    # Check for keywords to categorize
    if any(word in description for word in ['starbucks', 'restaurant', 'food', 'cafe', 'pizza']):
        return 'Food & Dining'
    elif any(word in description for word in ['amazon', 'walmart', 'store', 'shop']):
        return 'Shopping'
    elif any(word in description for word in ['uber', 'lyft', 'gas', 'fuel', 'parking']):
        return 'Transportation'
    elif any(word in description for word in ['netflix', 'spotify', 'movie', 'game']):
        return 'Entertainment'
    elif any(word in description for word in ['electric', 'water', 'internet', 'phone', 'insurance']):
        return 'Bills & Utilities'
    else:
        return 'Other'

# ===== PROCESS CSV FILE =====
def process_csv_file(filepath):
    """Read and process the CSV file"""
    try:
        # Read the CSV file
        df = pd.read_csv(filepath)
        
        # Find the right columns (handle different CSV formats)
        date_col = [col for col in df.columns if 'date' in col.lower()][0]
        desc_col = [col for col in df.columns if any(word in col.lower() for word in ['description', 'merchant', 'memo'])][0]
        amount_col = [col for col in df.columns if any(word in col.lower() for word in ['amount', 'total'])][0]
        
        # Rename columns to standard names
        df = df.rename(columns={
            date_col: 'date',
            desc_col: 'description',
            amount_col: 'amount'
        })
        
        # Clean the data
        df = df[['date', 'description', 'amount']].dropna()
        df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
        df['amount'] = pd.to_numeric(df['amount'])
        
        # Add categories
        df['category'] = df.apply(lambda row: categorize_transaction(row['description'], row['amount']), axis=1)
        
        return df, None
    except Exception as e:
        return None, str(e)

# ===== SAVE TO DATABASE =====
def save_to_database(df):
    """Save transactions to the database"""
    conn = sqlite3.connect('finance.db')
    df.to_sql('transactions', conn, if_exists='append', index=False)
    conn.close()

# ===== GET DATA FROM DATABASE =====
def get_all_transactions():
    """Get all transactions from database"""
    conn = sqlite3.connect('finance.db')
    df = pd.read_sql_query("SELECT * FROM transactions ORDER BY date DESC", conn)
    conn.close()
    return df

# ===== CALCULATE STATISTICS =====
def calculate_stats():
    """Calculate all the statistics for the dashboard"""
    df = get_all_transactions()
    
    if df.empty:
        return None
    
    # Calculate totals
    total_income = df[df['amount'] > 0]['amount'].sum()
    total_expenses = abs(df[df['amount'] < 0]['amount'].sum())
    net_savings = total_income - total_expenses
    
    # Category breakdown (expenses only)
    expenses_df = df[df['amount'] < 0].copy()
    expenses_df['amount'] = abs(expenses_df['amount'])
    category_totals = expenses_df.groupby('category')['amount'].sum().to_dict()
    
    # Monthly trend
    df['month'] = pd.to_datetime(df['date']).dt.to_period('M').astype(str)
    monthly_expenses = df[df['amount'] < 0].groupby('month')['amount'].sum().abs().to_dict()
    
    # Recent transactions (last 10)
    recent = df.head(10).to_dict('records')
    
    return {
        'total_income': round(total_income, 2),
        'total_expenses': round(total_expenses, 2),
        'net_savings': round(net_savings, 2),
        'categories': category_totals,
        'monthly': monthly_expenses,
        'recent': recent
    }

# ===== HTML TEMPLATE =====
HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>Finance Dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.plot.ly/plotly-2.26.0.min.js"></script>
    <style>
        body { background: #f5f5f5; padding: 20px; }
        .card { margin: 15px 0; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .stat-card { text-align: center; }
        .stat-value { font-size: 2.5rem; font-weight: bold; margin: 10px 0; }
        .income { color: #28a745; }
        .expense { color: #dc3545; }
        .upload-box { border: 3px dashed #ccc; padding: 40px; text-align: center; cursor: pointer; border-radius: 10px; }
        .upload-box:hover { background: #f0f0f0; border-color: #999; }
    </style>
</head>
<body>
    <div class="container">
        <h1 class="text-center mb-4">💰 Personal Finance Dashboard</h1>
        
        {% if not stats %}
            <!-- UPLOAD SECTION -->
            <div class="card">
                <h3 class="text-center">Upload Your Bank Statement</h3>
                <form action="/upload" method="post" enctype="multipart/form-data">
                    <div class="upload-box" onclick="document.getElementById('file').click()">
                        <h5>📁 Click to Upload CSV</h5>
                        <p>CSV should have: Date, Description, Amount</p>
                        <input type="file" id="file" name="file" accept=".csv" style="display:none" onchange="this.form.submit()">
                    </div>
                </form>
            </div>
        {% else %}
            <!-- SUMMARY CARDS -->
            <div class="row">
                <div class="col-md-4">
                    <div class="card stat-card">
                        <div>Total Income</div>
                        <div class="stat-value income">${{ stats.total_income }}</div>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="card stat-card">
                        <div>Total Expenses</div>
                        <div class="stat-value expense">${{ stats.total_expenses }}</div>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="card stat-card">
                        <div>Net Savings</div>
                        <div class="stat-value" style="color: {{ 'green' if stats.net_savings > 0 else 'red' }}">${{ stats.net_savings }}</div>
                    </div>
                </div>
            </div>
            
            <!-- CHARTS -->
            <div class="row">
                <div class="col-md-6">
                    <div class="card">
                        <h5>Spending by Category</h5>
                        <div id="categoryChart"></div>
                    </div>
                </div>
                <div class="col-md-6">
                    <div class="card">
                        <h5>Monthly Spending</h5>
                        <div id="monthlyChart"></div>
                    </div>
                </div>
            </div>
            
            <!-- RECENT TRANSACTIONS -->
            <div class="card">
                <h5>Recent Transactions</h5>
                <table class="table">
                    <thead>
                        <tr>
                            <th>Date</th>
                            <th>Description</th>
                            <th>Category</th>
                            <th>Amount</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for txn in stats.recent %}
                        <tr>
                            <td>{{ txn.date }}</td>
                            <td>{{ txn.description }}</td>
                            <td>{{ txn.category }}</td>
                            <td class="{{ 'income' if txn.amount > 0 else 'expense' }}">${{ "%.2f"|format(txn.amount|abs) }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            
            <!-- BUTTONS -->
            <div class="text-center mt-3">
                <a href="/upload" class="btn btn-primary">Upload More Data</a>
                <a href="/clear" class="btn btn-danger" onclick="return confirm('Clear all data?')">Clear Data</a>
            </div>
            
            <script>
                // Pie chart for categories
                var categoryData = {{ stats.categories | tojson }};
                Plotly.newPlot('categoryChart', [{
                    values: Object.values(categoryData),
                    labels: Object.keys(categoryData),
                    type: 'pie'
                }], {height: 300});
                
                // Bar chart for monthly spending
                var monthlyData = {{ stats.monthly | tojson }};
                Plotly.newPlot('monthlyChart', [{
                    x: Object.keys(monthlyData),
                    y: Object.values(monthlyData),
                    type: 'bar',
                    marker: {color: '#dc3545'}
                }], {height: 300});
            </script>
        {% endif %}
    </div>
</body>
</html>
'''

# ===== ROUTES (WEB PAGES) =====

@app.route('/')
def home():
    """Main page - shows dashboard or upload screen"""
    stats = calculate_stats()
    return render_template_string(HTML, stats=stats)

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    """Handle file upload"""
    if request.method == 'GET':
        return render_template_string(HTML, stats=None)
    
    # Get the uploaded file
    if 'file' not in request.files:
        return 'No file uploaded', 400
    
    file = request.files['file']
    
    if file.filename == '':
        return 'No file selected', 400
    
    if file and file.filename.endswith('.csv'):
        # Save the file temporarily
        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filepath)
        
        # Process it
        df, error = process_csv_file(filepath)
        
        if error:
            return f'Error: {error}', 400
        
        # Save to database
        save_to_database(df)
        
        # Delete the temporary file
        os.remove(filepath)
        
        # Go back to home page
        return redirect(url_for('home'))
    
    return 'Please upload a CSV file', 400

@app.route('/clear')
def clear():
    """Clear all data from database"""
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM transactions')
    conn.commit()
    conn.close()
    return redirect(url_for('home'))

# ===== START THE APP =====
if __name__ == '__main__':
    setup_database()  # Create database on first run
    print("\n✅ Server starting...")
    print("🌐 Open your browser and go to: http://localhost:5000\n")
    app.run(debug=True, port=5000)