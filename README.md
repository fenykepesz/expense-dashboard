# Personal Expense Dashboard

A beautiful, interactive expense tracking dashboard built with HTML, CSS, and Chart.js.

## 🎯 Features

- **Visual Analytics**: Interactive charts showing spending patterns
  - Monthly spending trends (line chart)
  - Category breakdown (doughnut chart)
  - Top merchants analysis (bar chart)
  - Card usage distribution (pie chart)

- **Smart Filtering**: Filter expenses by year, month, category, and card

- **Summary Cards**: Quick overview of total spending, average per transaction, and transaction count

- **Transaction List**: Detailed view of recent transactions

- **Hebrew Support**: Full RTL (Right-to-Left) language support

## 🚀 Live Demo

View the live dashboard: [Your GitHub Pages URL will be here]

## ⚠️ DISCLAIMER

**This tool is provided for educational and informational purposes only.**

- This dashboard is a visualization tool and does NOT provide financial advice
- I am not a financial advisor, accountant, or tax professional
- All financial data processing happens locally in your browser
- **You are solely responsible for:**
  - The accuracy of your financial data
  - Securing your personal financial information
  - Any financial decisions you make based on this tool
  - Compliance with applicable laws and regulations

**Security & Privacy:**
- Never commit real financial data to public repositories
- This tool does not transmit data to any server
- Keep your actual expense data files private and secure
- Use at your own risk

**No Warranty:**
This software is provided "AS IS" without warranty of any kind, express or implied. The author is not liable for any damages or losses resulting from use of this tool.

## 💻 Usage

1. Clone this repository
2. Open `index.html` in your browser
3. The dashboard will load sample data from `expense_data.json`

## 📊 Data Format

The dashboard expects data in the following JSON format:

```json
[
    {
        "date": "01/01/24",
        "merchant": "Merchant Name",
        "category": "Category Name",
        "card": "1234",
        "amount": 100.00,
        "month": "Jan 2024"
    }
]
```

## 🔒 Privacy & Data Security

**IMPORTANT:** This repository includes sample data only for demonstration purposes.

**To use with your real data:**
1. Clone/download this repository to your local computer
2. Replace `expense_data.json` with your own data (keep it LOCAL only)
3. Open `index.html` locally in your browser
4. **NEVER commit or upload your real financial data to GitHub or any public repository**

The `.gitignore` file is configured to help prevent accidentally committing private data files.

## 🛠️ Built With

- HTML5
- CSS3 (with modern gradients and animations)
- JavaScript (Vanilla)
- [Chart.js](https://www.chartjs.org/) - For data visualization

## 📝 License

MIT License - Feel free to use and modify this dashboard for your personal or commercial projects.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.

## 🤝 Contributing

Feel free to fork this project and submit pull requests with improvements!

---

 | Not affiliated with any financial institution
