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

View the live dashboard: https://github.com/fenykepesz/expense-dashboard

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

## 🔒 Privacy Note

This repository includes **sample data only**. Never commit your actual financial data to a public repository.

## 🛠️ Built With

- HTML5
- CSS3 (with modern gradients and animations)
- JavaScript (Vanilla)
- [Chart.js](https://www.chartjs.org/) - For data visualization

## 📝 License

Feel free to use and modify this dashboard for your personal projects (not commercial)

## 🤝 Contributing

Feel free to fork this project and submit pull requests with improvements!
