import os
import time
import hashlib
import requests
import unittest
import random
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackContext, CallbackQueryHandler
import asyncio
from telegram import error
from telegram.request import HTTPXRequest
import base64
import hmac
import qrcode
from io import BytesIO
from telegram import InputFile

# Access environment variables
SMILE_EMAIL = "renedysanasam13@gmail.com"
SMILE_UID = "913332"
SMILE_KEY = "84d312c4e0799bac1d363c87be2e14b7"
TELEGRAM_TOKEN = "7693779348:AAFCnsN8RQg-N5-Iy-wzFW9-1S3lFkw7cCY"
ADMIN_ID = "6501929376"  # Admin Telegram ID
UPI_ID = "BHARATPE09911990897@yesbankltd"
ADMIN_USERNAME = "@kendyenterprises"
BOT_NAME = "Kendy Top-up Bot"

# API URLs
PRODUCT_API_URL = "https://www.smile.one/smilecoin/api/product"
PRODUCT_LIST_API_URL = "https://www.smile.one/smilecoin/api/productlist"
SERVER_LIST_API_URL = "https://www.smile.one/smilecoin/api/getserver"
ROLE_QUERY_API_URL = "https://www.smile.one/smilecoin/api/getrole"
CREATE_ORDER_API_URL = "https://www.smile.one/smilecoin/api/createorder"

# Function to generate the 'sign' parameter
def generate_sign(params, key):
    """
    Generate the 'sign' parameter by sorting fields, concatenating them, appending the key,
    and applying double MD5 hashing.

    :param params: Dictionary of parameters to be signed
    :param key: The encryption key (SMILE_KEY)
    :return: The generated 'sign' parameter
    """
    sorted_params = sorted(params.items())
    query_string = "&".join(f"{k}={v}" for k, v in sorted_params)
    string_to_sign = f"{query_string}&{key}"
    return hashlib.md5(hashlib.md5(string_to_sign.encode()).hexdigest().encode()).hexdigest()

# Example of generating a real-time sign for Smile One API
def generate_real_time_sign():
    request_time = int(time.time())  # Current timestamp
    params = {
        "email": SMILE_EMAIL,
        "uid": SMILE_UID,
        "time": request_time,
    }
    sign = generate_sign(params, SMILE_KEY)
    return sign, request_time

# Example API request with real-time sign
def fetch_smile_one_balance():
    sign, request_time = generate_real_time_sign()
    params = {
        "email": SMILE_EMAIL,
        "uid": SMILE_UID,
        "time": request_time,
        "sign": sign,
    }

    response = requests.post(PRODUCT_API_URL, data=params)
    if response.status_code == 200:
        balance_data = response.json()
        balance = balance_data.get("balance", "N/A")  # Get the balance from the response
        print(f"Smile One Balance: ₹{balance}")
    else:
        print(f"Error fetching balance: {response.status_code}, {response.text}")

# In-memory product list
PRODUCT_LIST = []

# In-memory wallet for users
USER_WALLETS = {}

# In-memory reseller list
RESELLERS = set()


# Initialize the database
def init_db():
    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            productid TEXT PRIMARY KEY,
            productname TEXT NOT NULL,
            price REAL NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            userid TEXT PRIMARY KEY,
            username TEXT,
            balance REAL DEFAULT 0.0,
            total_spent REAL DEFAULT 0.0,
            register_date TEXT,
            role TEXT DEFAULT 'client'
        )
    """)
    conn.commit()
    conn.close()

# Ensure the database is initialized at the start of the program
init_db()

def update_db_schema():
    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    cursor.execute("""
        ALTER TABLE products ADD COLUMN reseller_price REAL DEFAULT 0.0
    """)
    conn.commit()
    conn.close()

# Call this function once to update the schema
# Uncomment the line below to run it
# update_db_schema()

def init_orders_table():
    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    # Drop the existing table if it exists (optional, for development purposes)
    # cursor.execute("DROP TABLE IF EXISTS orders")
    
    # Create the `orders` table with the `mlid` column
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,  -- Telegram ID
            mlid TEXT NOT NULL,    -- Mobile Legends ID
            zoneid TEXT NOT NULL,
            productname TEXT NOT NULL,
            price REAL NOT NULL,
            timestamp TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

# Call the function to ensure the table is initialized
init_orders_table()

def init_payments_table():
    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            userid TEXT NOT NULL,
            amount REAL NOT NULL,
            reference TEXT NOT NULL,
            status TEXT DEFAULT 'PENDING',
            timestamp TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

# Call the function to initialize the payments table
init_payments_table()

def remove_reseller_price_column():
    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()

    # Rename the existing table
    cursor.execute("ALTER TABLE products RENAME TO products_old")

    # Create a new table without the `reseller_price` column
    cursor.execute("""
        CREATE TABLE products (
            productid TEXT PRIMARY KEY,
            productname TEXT NOT NULL,
            price REAL NOT NULL
        )
    """)

    # Copy data from the old table to the new table
    cursor.execute("""
        INSERT INTO products (productid, productname, price)
        SELECT productid, productname, price FROM products_old
    """)

    # Drop the old table
    cursor.execute("DROP TABLE products_old")

    conn.commit()
    conn.close()

# Call this function once to remove the `reseller_price` column
# Uncomment the line below to execute it
# remove_reseller_price_column()

def add_mlid_column_to_orders():
    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    try:
        # Add the `mlid` column if it doesn't exist
        cursor.execute("ALTER TABLE orders ADD COLUMN mlid TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        # Column already exists
        print("Column `mlid` already exists in the `orders` table.")
    conn.close()

# Call the function to add the column
add_mlid_column_to_orders()

def add_reseller_price_column():
    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    try:
        # Add the `reseller_price` column if it doesn't exist
        cursor.execute("ALTER TABLE products ADD COLUMN reseller_price REAL DEFAULT 0.0")
        conn.commit()
    except sqlite3.OperationalError:
        # Column already exists
        print("Column `reseller_price` already exists in the `products` table.")
    conn.close()

# Call the function to add the column
add_reseller_price_column()

def add_user_id_column_to_orders():
    """
    Add the `user_id` column to the `orders` table if it doesn't exist.
    """
    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    try:
        # Add the `user_id` column if it doesn't exist
        cursor.execute("ALTER TABLE orders ADD COLUMN user_id TEXT")
        conn.commit()
        print("Column `user_id` added to the `orders` table.")
    except sqlite3.OperationalError:
        # Column already exists
        print("Column `user_id` already exists in the `orders` table.")
    conn.close()

# Call the function to ensure the column is added
add_user_id_column_to_orders()

def get_product_id_by_name(product_name):
    """
    Fetch the product ID from the database using the product name.
    """
    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    cursor.execute("SELECT productid FROM products WHERE productname LIKE ?", (f"%{product_name}%",))
    product = cursor.fetchone()
    conn.close()
    return product[0] if product else None

def get_order_details(order_id):
    """
    Fetch the MLID and Server ID from the order details using the order ID.
    """
    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    cursor.execute("SELECT mlid, zoneid FROM orders WHERE order_id = ?", (order_id,))
    order = cursor.fetchone()
    conn.close()
    return order if order else (None, None)

# Admin Commands
# Admin Command: Admin Panel with Plain Text
async def admin_panel(update: Update, context: CallbackContext) -> None:
    """
    Displays all admin commands as plain text (no buttons).
    """
    # Check if the user is the admin
    user_id = str(update.effective_user.id)
    if user_id != ADMIN_ID:
        await update.message.reply_text("Access Denied: You are not authorized to access the Admin Panel.")
        return

    # Send the admin panel commands as plain text
    admin_commands = """
🔧 Admin Panel Commands:
/addproduct - Add a new product
/updateprice - Update product price
/addresellerprice - Update reseller prices for products
/changeproduct - Change product details
/removeproduct - Remove a product
/removeproducts - Remove multiple products
/viewproductlist - View the product list
/manageproduct - Manage product categories
/fetchbalance - Fetch Smile One balance
/serverlist - Get server list
/viewusers - View all users
/viewpayments - View pending payments
/verifypayment - Verify a payment
/rejectpayment - Reject a payment
/addreseller - Add a reseller
/removereseller - Remove a reseller
/broadcast - Broadcast a message
/addfunds - Add funds to a user's wallet
/generatecode - Generate Redeem Code
"""
    await update.message.reply_text(admin_commands)

# Callback handler for admin buttons
async def admin_button_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    print(f"Button clicked: {query.data}")  # Debug message
    await query.answer()  # Acknowledge the callback

    # Handle button clicks based on callback_data
    if query.data == "addproduct":
        await query.edit_message_text("Use /addproduct <productid,productname,price>; <productid,productname,price>; ... to add products.")
    elif query.data == "manageproduct":
        await query.edit_message_text(
            "Use /manageproduct <productid1,category1;productid2,category2;...>\n"
            "Categories: diamond, bonus, wkp"
        )
    elif query.data == "addfunds":
        await query.edit_message_text("Use /addfunds <userid> <amount> to add funds to a user's wallet.")
    elif query.data == "updateprice":
        await query.edit_message_text("Use /updateprice <productid> <newprice> to update a product's price.")
    elif query.data == "changeproduct":
        await query.edit_message_text("Use /changeproduct <productid> <newname> <newprice> to change product details.")
    elif query.data == "removeproduct":
        await query.edit_message_text("Use /removeproduct <productid> to remove a product.")
    elif query.data == "viewproductlist":
        # Display the product list
        conn = sqlite3.connect("wallet.db")
        cursor = conn.cursor()
        cursor.execute("SELECT productid, productname, price FROM products")
        products = cursor.fetchall()
        conn.close()

        if not products:
            await query.edit_message_text("No products available.")
        else:
            product_message = "Product List:\n"
            for productid, productname, price in products:
                product_message += f"ID: {productid}: 💎 {productname}: ₹ {price}\n"
            await query.edit_message_text(product_message)
    elif query.data == "fetchbalance":
        # Fetch balance from Smile One
        request_time = int(time.time())
        params = {
            "email": SMILE_EMAIL,
            "uid": SMILE_UID,
            "time": request_time,
        }
        sign = generate_sign(params, SMILE_KEY)
        payload = {**params, "sign": sign}

        response = requests.post(PRODUCT_API_URL, data=payload)
        if response.status_code == 200:
            balance_data = response.json()
            balance = balance_data.get("balance", "N/A")  # Get the balance from the response
            await query.edit_message_text(f"Smile One Balance: ₹{balance}")
        else:
            await query.edit_message_text(f"Error fetching balance: {response.status_code}, {response.text}")
    elif query.data == "serverlist":
        await query.edit_message_text("Use /serverlist <userid> to get the server list for a user.")
    elif query.data == "viewusers":
        # Display user wallet balances
        if not USER_WALLETS:
            await query.edit_message_text("No users found.")
        else:
            user_message = "User Wallets:\n"
            for userid, balance in USER_WALLETS.items():
                user_message += f"User ID: {userid}, Balance: ₹{balance:.2f}\n"
            await query.edit_message_text(user_message)
    elif query.data == "manageresellers":
        await query.edit_message_text("Use /addreseller <userid> to add a reseller.\nUse /removereseller <userid> to remove a reseller.")

async def handle_button_click(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()  # Acknowledge the callback

    # Handle button clicks based on callback_data
    if query.data == "diamond":
        # Trigger the /diamond command to show the diamond list
        await show_diamonds_command(update, context)
    elif query.data == "wkp":
        await show_weekly_pass_command(update, context)
    elif query.data == "bonus":
        await show_bonus_command(update, context)
    elif query.data == "wallet":
        await wallet_command(update, context)
    elif query.data == "buy":
        await query.edit_message_text("🛒 Use /buy <amount> to add funds to your wallet.")
    elif query.data == "topup":
        await query.edit_message_text("⚡ Use /topup <userid> <zoneid> <productname> to purchase a product.")

async def product_list_command(update: Update, context: CallbackContext) -> None:
    # Check if the user is the admin
    user_id = str(update.effective_user.id)
    if user_id != ADMIN_ID:
        await update.message.reply_text("Access Denied: This command is for Admins only.")
        return

    # Check if the required arguments are provided
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /productlist <userid>")
        return

    # Extract `userid` from the command arguments
    userid = context.args[0]
    product = "mobilelegends"
    request_time = int(time.time())

    # Prepare the parameters
    params = {
        "email": SMILE_EMAIL,
        "uid": SMILE_UID,
        "userid": userid,
        "product": product,
        "time": request_time,
    }
    sign = generate_sign(params, SMILE_KEY)
    payload = {**params, "sign": sign}

    # Make the API request
    response = requests.post(PRODUCT_LIST_API_URL, data=payload)
    if response.status_code == 200:
        await update.message.reply_text(f"Product List API Response: {response.json()}")
    else:
        await update.message.reply_text(f"Error: {response.status_code}, {response.text}")

async def server_list_command(update: Update, context: CallbackContext) -> None:
    # Check if the user is the admin
    user_id = str(update.effective_user.id)
    if user_id != ADMIN_ID:
        await update.message.reply_text("Access Denied: This command is for Admins only.")
        return

    # Check if the required arguments are provided
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /serverlist <userid>")
        return

    # Extract `userid` from the command arguments
    userid = context.args[0]
    product = "ragnarokm"
    request_time = int(time.time())

    # Prepare the parameters
    params = {
        "email": SMILE_EMAIL,
        "uid": SMILE_UID,
        "userid": userid,
        "product": product,
        "time": request_time,
    }
    sign = generate_sign(params, SMILE_KEY)
    payload = {**params, "sign": sign}

    # Make the API request
    response = requests.post(SERVER_LIST_API_URL, data=payload)
    if response.status_code == 200:
        await update.message.reply_text(f"Server List API Response: {response.json()}")
    else:
        await update.message.reply_text(f"Error: {response.status_code}, {response.text}")

# Admin Command: Add Product
async def add_product_command(update: Update, context: CallbackContext) -> None:
    # Check if the user is the admin
    user_id = str(update.effective_user.id)
    if user_id != ADMIN_ID:
        await update.message.reply_text("Access Denied: You are not authorized to add products.")
        return

    # Check if the required arguments are provided
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /addproduct <productid,productname,price>; ...")
        return

    # Parse the input for multiple products
    products_input = " ".join(context.args)  # Combine all arguments into a single string
    products = products_input.split(";")  # Split by semicolon to get individual products

    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    added_products = []
    failed_products = []

    for product in products:
        product_details = product.strip().split(",")  # Split by comma to get product details
        if len(product_details) != 3:
            failed_products.append(f"Invalid format: {product.strip()}")
            continue

        productid, productname, price = product_details
        try:
            price = float(price)  # Convert price to float
            cursor.execute(
                "INSERT INTO products (productid, productname, price) VALUES (?, ?, ?)",
                (productid.strip(), productname.strip(), price)
            )
            conn.commit()
            added_products.append(f"ID: {productid.strip()}, 💎 {productname.strip()}, ₹ {price}")
        except sqlite3.IntegrityError:
            failed_products.append(f"Duplicate ID: {productid.strip()}")
        except ValueError:
            failed_products.append(f"Invalid price: {product.strip()}")

    conn.close()

    # Prepare the response message
    response_message = ""
    if added_products:
        response_message += "Products added successfully:\n" + "\n".join(added_products) + "\n"
    if failed_products:
        response_message += "Failed to add the following products:\n" + "\n".join(failed_products)

    await update.message.reply_text(response_message)

# Admin Command: Update Product Price
async def update_product_price_command(update: Update, context: CallbackContext) -> None:
    """
    Allows the admin to update the prices of multiple products in bulk.
    """
    # Check if the user is the admin
    user_id = str(update.effective_user.id)
    if user_id != ADMIN_ID:
        await update.message.reply_text("Access Denied: You are not authorized to update product prices.")
        return

    # Check if the required arguments are provided
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /updateprice <productid1,newprice1;productid2,newprice2;...>")
        return

    # Parse the input for multiple products
    products_input = " ".join(context.args)  # Combine all arguments into a single string
    products = products_input.split(";")  # Split by semicolon to get individual product-price pairs

    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    updated_products = []
    failed_products = []

    for product in products:
        product_details = product.strip().split(",")  # Split by comma to get product ID and new price
        if len(product_details) != 2:
            failed_products.append(f"Invalid format: {product.strip()}")
            continue

        productid, new_price = product_details
        try:
            new_price = float(new_price)  # Convert new price to float
            cursor.execute("UPDATE products SET price = ? WHERE productid = ?", (new_price, productid.strip()))
            if cursor.rowcount > 0:
                conn.commit()
                updated_products.append(f"Product ID: {productid.strip()} updated to ₹{new_price:.2f}")
            else:
                failed_products.append(f"Product not found: {product.strip()}")
        except ValueError:
            failed_products.append(f"Invalid price: {product.strip()}")

    conn.close()

    # Prepare the response message
    response_message = ""
    if updated_products:
        response_message += "Products updated successfully:\n" + "\n".join(updated_products) + "\n"
    if failed_products:
        response_message += "Failed to update the following products:\n" + "\n".join(failed_products)

    await update.message.reply_text(response_message)

# Admin Command: Remove Product
async def remove_product_command(update: Update, context: CallbackContext) -> None:
    # Check if the user is the admin
    user_id = str(update.effective_user.id)
    if user_id != ADMIN_ID:
        await update.message.reply_text("Access Denied: You are not authorized to remove products.")
        return

    # Check if the required arguments are provided
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /removeproduct <productid>")
        return

    # Extract product ID
    productid = context.args[0]

    # Remove the product from the database
    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM products WHERE productid = ?", (productid,))
    if cursor.rowcount > 0:
        conn.commit()
        await update.message.reply_text(f"Product with ID {productid} removed successfully.")
    else:
        await update.message.reply_text(f"Product with ID {productid} not found.")
    conn.close()

# Admin Command: Remove Products
async def remove_products_command(update: Update, context: CallbackContext) -> None:
    """
    Allows the admin to remove multiple products in bulk.
    """
    # Check if the user is the admin
    user_id = str(update.effective_user.id)
    if user_id != ADMIN_ID:
        await update.message.reply_text("Access Denied: You are not authorized to remove products.")
        return

    # Check if the required arguments are provided
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /removeproducts <productid1;productid2;...>")
        return

    # Parse the input for multiple product IDs
    product_ids_input = " ".join(context.args)  # Combine all arguments into a single string
    product_ids = product_ids_input.split(";")  # Split by semicolon to get individual product IDs

    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    removed_products = []
    failed_products = []

    for product_id in product_ids:
        product_id = product_id.strip()
        cursor.execute("DELETE FROM products WHERE productid = ?", (product_id,))
        if cursor.rowcount > 0:
            conn.commit()
            removed_products.append(product_id)
        else:
            failed_products.append(product_id)

    conn.close()

    # Prepare the response message
    response_message = ""
    if removed_products:
        response_message += "Products removed successfully:\n" + "\n".join(removed_products) + "\n"
    if failed_products:
        response_message += "Failed to remove the following products (not found):\n" + "\n".join(failed_products)

    await update.message.reply_text(response_message)

# Admin Command: Change Product Details
async def change_product_details_command(update: Update, context: CallbackContext) -> None:
    # Check if the user is the admin
    user_id = str(update.effective_user.id)
    if user_id != ADMIN_ID:
        await update.message.reply_text("Access Denied: You are not authorized to change product details.")
        return

    # Check if the required arguments are provided
    if len(context.args) < 3:
        await update.message.reply_text("Usage: /changeproduct <productid> <newname> <newprice>")
        return

    # Extract product ID, new name, and new price
    productid = context.args[0]
    new_name = context.args[1]
    try:
        new_price = float(context.args[2])
    except ValueError:
        await update.message.reply_text("Invalid price. Please provide a valid number.")
        return

    # Update the product details in the database
    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE products SET productname = ?, price = ? WHERE productid = ?", (new_name, new_price, productid))
    if cursor.rowcount > 0:
        conn.commit()
        await update.message.reply_text(f"Product details updated successfully for ID: {productid}. New Name: {new_name}, New Price: ₹{new_price}")
    else:
        await update.message.reply_text(f"Product with ID {productid} not found.")
    conn.close()

# Admin Command: Add Reseller
async def add_reseller_command(update: Update, context: CallbackContext) -> None:
    """
    Allows the admin to assign the 'reseller' role to a user.
    """
    # Check if the user is the admin
    user_id = str(update.effective_user.id)
    if user_id != ADMIN_ID:
        await update.message.reply_text("Access Denied: You are not authorized to add resellers.")
        return

    # Check if the required arguments are provided
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /addreseller <userid>")
        return

    # Extract the user ID to be assigned as a reseller
    reseller_id = context.args[0]

    # Update the user's role in the database
    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE userid = ?", (reseller_id,))
    user_data = cursor.fetchone()

    if not user_data:
        await update.message.reply_text(f"User with ID {reseller_id} not found.")
        conn.close()
        return

    cursor.execute("UPDATE users SET role = 'reseller' WHERE userid = ?", (reseller_id,))
    conn.commit()
    conn.close()

    await update.message.reply_text(f"User with ID {reseller_id} has been successfully added as a reseller.")

# Admin Command: Remove Reseller
async def remove_reseller_command(update: Update, context: CallbackContext) -> None:
    """
    Allows the admin to remove the 'reseller' role from a user.
    """
    # Check if the user is the admin
    user_id = str(update.effective_user.id)
    if user_id != ADMIN_ID:
        await update.message.reply_text("Access Denied: You are not authorized to remove resellers.")
        return

    # Check if the required arguments are provided
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /removereseller <userid>")
        return

    # Extract the user ID to be removed as a reseller
    reseller_id = context.args[0]

    # Update the user's role in the database
    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE userid = ?", (reseller_id,))
    user_data = cursor.fetchone()

    if not user_data:
        await update.message.reply_text(f"User with ID {reseller_id} not found.")
        conn.close()
        return

    cursor.execute("UPDATE users SET role = 'client' WHERE userid = ?", (reseller_id,))
    conn.commit()
    conn.close()

    await update.message.reply_text(f"User with ID {reseller_id} has been successfully removed as a reseller.")

# Admin Command: View Pending Payments
async def view_payments_command(update: Update, context: CallbackContext) -> None:
    # Check if the user is the admin
    user_id = str(update.effective_user.id)
    if user_id != ADMIN_ID:
        await update.message.reply_text("Access Denied: You are not authorized to view payments.")
        return

    # Fetch pending payments from the database
    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    cursor.execute("SELECT payment_id, userid, amount, reference, timestamp FROM payments WHERE status = 'PENDING'")
    payments = cursor.fetchall()
    conn.close()

    # Check if there are any pending payments
    if not payments:
        await update.message.reply_text("No pending payments.")
        return

    # Format the pending payments for display
    payment_message = "Pending Payments:\n"
    for payment_id, userid, amount, reference, timestamp in payments:
        payment_message += f"""
Payment ID: {payment_id}
User ID: {userid}
Amount: ₹{amount:.2f}
Reference: {reference}
Date: {timestamp}
---
"""
    await update.message.reply_text(payment_message)

# Admin Command: Verify Payment
async def verify_payment_command(update: Update, context: CallbackContext) -> None:
    # Check if the user is the admin
    user_id = str(update.effective_user.id)
    if user_id != ADMIN_ID:
        await update.message.reply_text("Access Denied: You are not authorized to verify payments.")
        return

    # Check if the required arguments are provided
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /verifypayment <payment_id>")
        return

    # Extract `payment_id` from the command arguments
    try:
        payment_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid payment ID. Please provide a valid number.")
        return

    # Fetch the payment details from the database
    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    cursor.execute("SELECT userid, amount FROM payments WHERE payment_id = ? AND status = 'PENDING'", (payment_id,))
    payment = cursor.fetchone()

    if not payment:
        await update.message.reply_text(f"Payment with ID {payment_id} not found or already verified.")
        conn.close()
        return

    userid, amount = payment

    # Add funds to the user's wallet
    if userid not in USER_WALLETS:
        USER_WALLETS[userid] = 0.0
    USER_WALLETS[userid] += amount

    # Update the payment status to "VERIFIED"
    cursor.execute("UPDATE payments SET status = 'VERIFIED' WHERE payment_id = ?", (payment_id,))
    conn.commit()
    conn.close()

    await update.message.reply_text(f"Payment with ID {payment_id} verified successfully! ₹{amount:.2f} added to user {userid}'s wallet.")

# Admin Command: Reject Payment
async def reject_payment_command(update: Update, context: CallbackContext) -> None:
    # Check if the user is the admin
    user_id = str(update.effective_user.id)
    if user_id != ADMIN_ID:
        await update.message.reply_text("Access Denied: You are not authorized to reject payments.")
        return

    # Check if the required arguments are provided
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /rejectpayment <payment_id>")
        return

    # Extract `payment_id` from the command arguments
    try:
        payment_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid payment ID. Please provide a valid number.")
        return

    # Fetch the payment details from the database
    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    cursor.execute("SELECT userid, amount FROM payments WHERE payment_id = ? AND status = 'PENDING'", (payment_id,))
    payment = cursor.fetchone()

    if not payment:
        await update.message.reply_text(f"Payment with ID {payment_id} not found or already processed.")
        conn.close()
        return

    userid, amount = payment

    # Update the payment status to "REJECTED"
    cursor.execute("UPDATE payments SET status = 'REJECTED' WHERE payment_id = ?", (payment_id,))
    conn.commit()
    conn.close()

    # Notify the admin and the user
    await update.message.reply_text(f"Payment with ID {payment_id} has been rejected.")
    try:
        await context.bot.send_message(chat_id=userid, text=f"Your payment of ₹{amount:.2f} with ID {payment_id} has been rejected by the admin.")
    except Exception as e:
        await update.message.reply_text(f"Failed to notify the user: {e}")

# Admin Command: Manage Product Categories
async def manage_product_command(update: Update, context: CallbackContext) -> None:
    # Check if the user is the admin
    user_id = str(update.effective_user.id)
    if user_id != ADMIN_ID:
        await update.message.reply_text("Access Denied: You are not authorized to manage products.")
        return

    # Check if the required arguments are provided
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /manageproduct <productid> <category>\nCategories: diamond, doublediamond, wkp")
        return

    # Extract product ID and category
    productid = context.args[0]
    category = context.args[1].lower()

    # Validate the category
    valid_categories = ["diamond", "doublediamond", "wkp"]
    if category not in valid_categories:
        await update.message.reply_text(f"Invalid category. Valid categories are: {', '.join(valid_categories)}")
        return

    # Update the product category in the database
    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE products SET productname = productname || ' [%s]' WHERE productid = ?" % category.capitalize(), (productid,))
    if cursor.rowcount > 0:
        conn.commit()
        await update.message.reply_text(f"Product with ID {productid} has been categorized as {category.capitalize()}.")
    else:
        await update.message.reply_text(f"Product with ID {productid} not found.")
    conn.close()

# Admin Command: Bulk Manage Product Categories
async def manage_product_command(update: Update, context: CallbackContext) -> None:
    # Check if the user is the admin
    user_id = str(update.effective_user.id)
    if user_id != ADMIN_ID:
        await update.message.reply_text("Access Denied: You are not authorized to manage products.")
        return

    # Check if the required arguments are provided
    if len(context.args) < 1:
        await update.message.reply_text(
            "Usage: /manageproduct <productid1,category1;productid2,category2;...>\n"
            "Categories: diamond, bonus, wkp"
        )
        return

    # Parse the input for multiple products
    products_input = " ".join(context.args)  # Combine all arguments into a single string
    products = products_input.split(";")  # Split by semicolon to get individual product-category pairs

    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    updated_products = []
    failed_products = []

    for product in products:
        product_details = product.strip().split(",")  # Split by comma to get product ID and category
        if len(product_details) != 2:
            failed_products.append(f"Invalid format: {product.strip()}")
            continue

        productid, category = product_details
        category = category.lower()

        # Validate the category
        valid_categories = ["diamond", "bonus", "wkp"]
        if category not in valid_categories:
            failed_products.append(f"Invalid category: {product.strip()}")
            continue

        # Check if the product exists in the database
        cursor.execute("SELECT * FROM products WHERE productid = ?", (productid.strip(),))
        if not cursor.fetchone():
            failed_products.append(f"Product not found: {product.strip()}")
            continue

        # Update the product category in the database
        cursor.execute(
            "UPDATE products SET productname = productname || ' [%s]' WHERE productid = ?" % category.capitalize(),
            (productid.strip(),)
        )
        if cursor.rowcount > 0:
            conn.commit()
            updated_products.append(f"Product ID: {productid.strip()} categorized as {category.capitalize()}")
        else:
            failed_products.append(f"Failed to update: {product.strip()}")

    conn.close()

    # Prepare the response message
    response_message = ""
    if updated_products:
        response_message += "Products updated successfully:\n" + "\n".join(updated_products) + "\n"
    if failed_products:
        response_message += "Failed to update the following products:\n" + "\n".join(failed_products)

    await update.message.reply_text(response_message)

async def view_users_command(update: Update, context: CallbackContext) -> None:
    """
    Allows the admin to view all registered users and their details.
    """
    # Check if the user is the admin
    user_id = str(update.effective_user.id)
    if user_id != ADMIN_ID:
        await update.message.reply_text("Access Denied: You are not authorized to view users.")
        return

    # Fetch all users from the database
    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT userid, username, balance, total_spent, register_date, role
        FROM users
        ORDER BY register_date ASC
    """)
    users = cursor.fetchall()
    conn.close()

    if not users:
        await update.message.reply_text("No users found.")
        return

    # Format the user list for display
    user_message = "Registered Users:\n"
    for userid, username, balance, total_spent, register_date, role in users:
        user_message += f"""
Your Account Details:
---------------------------------
🆔 User ID: {userid}
👤 Username: {username}
💰 Balance: ₹{balance:.2f}
📅 Registered On: {register_date}
🔖 Role: {role.capitalize()}
---
"""
    await update.message.reply_text(user_message)

# Admin Command: Broadcast Message
async def broadcast_command(update: Update, context: CallbackContext) -> None:
    """
    Allows the admin to broadcast a message to all registered users.
    """
    # Check if the user is the admin
    user_id = str(update.effective_user.id)
    if user_id != ADMIN_ID:
        await update.message.reply_text("Access Denied: You are not authorized to broadcast messages.")
        return

    # Check if the message to broadcast is provided
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /broadcast <message>")
        return

    # Combine all arguments into the broadcast message
    broadcast_message = " ".join(context.args)

    # Fetch all registered users from the database
    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    cursor.execute("SELECT userid FROM users")
    users = cursor.fetchall()
    conn.close()

    if not users:
        await update.message.reply_text("No registered users to broadcast the message.")
        return

    # Send the broadcast message to all users
    failed_users = []
    for (userid,) in users:
        try:
            await context.bot.send_message(chat_id=userid, text=broadcast_message)
        except Exception as e:
            failed_users.append(userid)

    # Notify the admin about the broadcast status
    if failed_users:
        await update.message.reply_text(f"Broadcast completed, but failed to send to the following users: {', '.join(map(str, failed_users))}")
    else:
        await update.message.reply_text("Broadcast message sent successfully to all users.")

# Admin Command: Add Funds
async def fund_command(update: Update, context: CallbackContext) -> None:
    """
    Allows the admin to add funds to a user's wallet using their Telegram ID.
    """
    # Check if the user is the admin
    user_id = str(update.effective_user.id)
    if user_id != ADMIN_ID:
        await update.message.reply_text("Access Denied: You are not authorized to add funds.")
        return

    # Check if the required arguments are provided
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /fund <telegram_id> <amount>")
        return

    # Extract `telegram_id` and `amount` from the command arguments
    telegram_id = context.args[0]
    try:
        amount = float(context.args[1])
        if amount <= 0:
            raise ValueError("Amount must be greater than zero.")
    except ValueError:
        await update.message.reply_text("Invalid amount. Please provide a valid number greater than zero.")
        return

    # Add funds to the user's wallet in the database
    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()

    # Check if the user exists in the database
    cursor.execute("SELECT balance FROM users WHERE userid = ?", (telegram_id,))
    user_data = cursor.fetchone()

    if not user_data:
        await update.message.reply_text("User not found. Please register using /start.")
        return

    current_balance = user_data[0]
    new_balance = current_balance + amount
    cursor.execute("UPDATE users SET balance = ? WHERE userid = ?", (new_balance, telegram_id))
    conn.commit()
    conn.close()

    # Notify the admin and the user
    await update.message.reply_text(f"Successfully added ₹{amount:.2f} to user {telegram_id}'s wallet. Current Balance: ₹{new_balance:.2f}")
    try:
        await context.bot.send_message(chat_id=telegram_id, text=f"₹{amount:.2f} has been added to your wallet by the admin. Current Balance: ₹{new_balance:.2f}")
    except Exception as e:
        await update.message.reply_text(f"Failed to notify the user: {e}")

# Admin Command: Add Reseller Price
async def add_reseller_price_command(update: Update, context: CallbackContext) -> None:
    """
    Allows the admin to set reseller prices for all products.
    """
    # Check if the user is the admin
    user_id = str(update.effective_user.id)
    if user_id != ADMIN_ID:
        await update.message.reply_text("Access Denied: You are not authorized to update reseller prices.")
        return

    # Check if the required arguments are provided
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /addresellerprice <productid1,newprice1;productid2,newprice2;...>")
        return

    # Parse the input for multiple products
    products_input = " ".join(context.args)  # Combine all arguments into a single string
    products = products_input.split(";")  # Split by semicolon to get individual product-price pairs

    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    updated_products = []
    failed_products = []

    for product in products:
        product_details = product.strip().split(",")  # Split by comma to get product ID and new reseller price
        if len(product_details) != 2:
            failed_products.append(f"Invalid format: {product.strip()}")
            continue

        productid, new_reseller_price = product_details
        try:
            new_reseller_price = float(new_reseller_price)  # Convert new price to float
            cursor.execute("UPDATE products SET reseller_price = ? WHERE productid = ?", (new_reseller_price, productid.strip()))
            if cursor.rowcount > 0:
                conn.commit()
                updated_products.append(f"Product ID: {productid.strip()} updated to Reseller Price ₹{new_reseller_price:.2f}")
            else:
                failed_products.append(f"Product not found: {product.strip()}")
        except ValueError:
            failed_products.append(f"Invalid price: {product.strip()}")

    conn.close()

    # Prepare the response message
    response_message = ""
    if updated_products:
        response_message += "Reseller prices updated successfully:\n" + "\n".join(updated_products) + "\n"
    if failed_products:
        response_message += "Failed to update the following products:\n" + "\n".join(failed_products)

    await update.message.reply_text(response_message)

# User Commands
async def user_panel(update: Update, context: CallbackContext) -> None:
    commands = """
User Panel Commands:
/role <userid> <zoneid> - Query role information
/purchase <userid> <zoneid> <productid> - Create an order
/showproducts - Show available products
"""
    await update.message.reply_text(commands)

async def reseller_panel(update: Update, context: CallbackContext) -> None:
    """
    Displays all reseller commands as plain text.
    """
    # Check if the user is a reseller
    user_id = str(update.effective_user.id)
    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM users WHERE userid = ?", (user_id,))
    user_data = cursor.fetchone()
    conn.close()

    if not user_data or user_data[0] != "reseller":
        await update.message.reply_text("Access Denied: You are not authorized to view reseller products. Contact admin {ADMIN_USERNAME}")
        return

    # Send the reseller panel commands as plain text
    reseller_commands = """
🔧 Reseller Panel Commands:
/viewresellerproducts - View reseller-specific product prices
/viewresellerorders - View your order history
"""
    await update.message.reply_text(reseller_commands)

async def role_query_command(update: Update, context: CallbackContext) -> None:
    """
    Fetch the Mobile Legends username using the Smile.One API and display it in the desired format.
    """
    # Check if the required arguments are provided
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /role <userid> <zoneid>")
        return

    # Extract `userid` and `zoneid` from the command arguments
    userid = context.args[0]
    zoneid = context.args[1]
    product_id = "13"  # Example product ID
    product = "mobilelegends"  # Example product type
    request_time = int(time.time())

    # Prepare the parameters for the API request
    params = {
        "email": SMILE_EMAIL,
        "uid": SMILE_UID,
        "userid": userid,
        "zoneid": zoneid,
        "productid": product_id,
        "product": product,
        "time": request_time,
    }
    sign = generate_sign(params, SMILE_KEY)
    payload = {**params, "sign": sign}

    # Make the API request to fetch the user details
    response = requests.post(ROLE_QUERY_API_URL, data=payload)
    if response.status_code == 200:
        response_data = response.json()

        # Extract relevant details from the response
        username = response_data.get("username", "Unknown")
        user_id = response_data.get("user_id", "Unknown")
        zone_id = response_data.get("zone_id", "Unknown")

        # Format the response message
        role_message = f"""
✅ Mobile Legends User Details:
User ID: {userid}
Zone ID: {zoneid}
Username: {username}
"""
        await update.message.reply_text(role_message)
    else:
        # Handle API errors
        await update.message.reply_text(
            f"Error fetching user details: {response.status_code}, {response.text}"
        )

async def purchase_command(update: Update, context: CallbackContext) -> None:
    if len(context.args) < 3:
        await update.message.reply_text("Usage: /purchase <userid> <zoneid> <productid>")
        return

    userid = context.args[0]
    zoneid = context.args[1]
    productid = context.args[2]
    product = "mobilelegends"
    request_time = int(time.time())

    params = {
        "email": SMILE_EMAIL,
        "uid": SMILE_UID,
        "userid": userid,
        "zoneid": zoneid,
        "product": product,
        "productid": productid,
        "time": request_time,
    }
    sign = generate_sign(params, SMILE_KEY)
    payload = {**params, "sign": sign}

    response = requests.post(CREATE_ORDER_API_URL, data=payload)
    if response.status_code == 200:
        await update.message.reply_text(f"Purchase API Response: {response.json()}")
    else:
        await update.message.reply_text(f"Error: {response.status_code}, {response.text}")

async def topup_command(update: Update, context: CallbackContext) -> None:
    """
    Create up to 10 orders to Smile.One for recharging Mobile Legends diamonds using the user's available balance.
    Users can order a single product multiple times or multiple products.
    """
    # Check if the required arguments are provided
    if len(context.args) < 3:
        await update.message.reply_text("Usage: /topup <ml_id> <serverid> <productname> <quantity>")
        return

    # Extract `ml_id`, `serverid`, and product names from the command arguments
    ml_id = context.args[0]
    serverid = context.args[1]
    productnames = " ".join(context.args[2:]).split(";")  # Split product names by semicolon

    if len(productnames) > 10:
        await update.message.reply_text("You can only create up to 10 orders at a time.")
        return

    # Fetch the user's balance using their Telegram ID
    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    telegram_id = str(update.effective_user.id)
    cursor.execute("SELECT balance FROM users WHERE userid = ?", (telegram_id,))
    user_data = cursor.fetchone()

    if not user_data:
        await update.message.reply_text("User not found. Please register using /start.")
        conn.close()
        return

    balance = user_data[0]
    total_cost = 0
    orders = []

    # Process each product
    for product_entry in productnames:
        product_entry = product_entry.strip()
        if "x" in product_entry:  # Check if the user wants to order a single product multiple times
            productname, quantity = product_entry.split("x")
            try:
                quantity = int(quantity)
                if quantity <= 0 or quantity > 10:
                    await update.message.reply_text(f"Invalid quantity for '{productname}'. Must be between 1 and 10.")
                    continue
            except ValueError:
                await update.message.reply_text(f"Invalid quantity format for '{productname}'. Use 'productnamexN'.")
                continue
        else:
            productname = product_entry
            quantity = 1

        cursor.execute("SELECT productid, price FROM products WHERE productname LIKE ?", (f"%{productname}%",))
        product = cursor.fetchone()

        if not product:
            await update.message.reply_text(f"Product '{productname}' not found. Skipping this product.")
            continue

        productid, price = product
        total_cost += price * quantity

        # Check if the user has enough funds for all orders
        if total_cost > balance:
            await update.message.reply_text(f"Insufficient funds for all orders. Total cost: ₹{total_cost:.2f}, Available balance: ₹{balance:.2f}.")
            conn.close()
            return

        # Add the order(s) to the list
        for _ in range(quantity):
            orders.append((productid, productname, price))

    # Deduct the total cost from the user's wallet
    new_balance = balance - total_cost
    cursor.execute("UPDATE users SET balance = ? WHERE userid = ?", (new_balance, telegram_id))
    conn.commit()

    # Process each order with the Smile.One API
    successful_orders = []
    failed_orders = []
    for productid, productname, price in orders:
        request_time = int(time.time())
        params = {
            "email": SMILE_EMAIL,
            "uid": SMILE_UID,
            "userid": ml_id,  # Use Mobile Legends ID here
            "zoneid": serverid,
            "product": "mobilelegends",
            "productid": productid,
            "time": request_time,
        }
        sign = generate_sign(params, SMILE_KEY)
        payload = {**params, "sign": sign}

        # Make the API request to create an order
        response = requests.post(CREATE_ORDER_API_URL, data=payload)
        if response.status_code == 200:
            response_data = response.json()
            order_id = response_data.get("order_id", "Unknown")

            # Fetch the IGN (In-Game Name) using the role_query API
            ign = await fetch_ign(order_id, productname)

            # Save the order details to the database
            cursor.execute("""
                INSERT INTO orders (order_id, userid, mlid, zoneid, productname, price, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (order_id, telegram_id, ml_id, serverid, productname, price, time.strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()

            successful_orders.append(f"""
📜 Order ID: {order_id}
👤 IGN: {ign}
🆔 User ID: {ml_id}
🌍 Server ID: {serverid}
🏷️ Product: {productname}
💸 Price: ₹{price:.2f}

""")
        else:
            failed_orders.append(f"Product: {productname}, Error: {response.status_code}, {response.text}")

    conn.close()

    # Prepare the response message
    response_message = "🛒 Order Summary:\n"
    if successful_orders:
        response_message += "✅ Successful Orders\n" + "\n".join(successful_orders) + "\n"
        response_message += "🎉 Your order has been successfully placed! Thank you for using our service.\n"
    if failed_orders:
        response_message += "❌ Failed Orders\n" + "\n".join(failed_orders) + "\n"
    response_message += f"💰 Remaining Balance: ₹{new_balance:.2f}"

    await update.message.reply_text(response_message)

# User Command: Show Products
async def show_diamonds_command(update: Update, context: CallbackContext) -> None:
    """
    Fetch and display the available diamond products from the database.
    """
    # Get the user's Telegram ID
    user_id = str(update.effective_user.id)

    # Check if the user is a reseller
    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM users WHERE userid = ?", (user_id,))
    user_data = cursor.fetchone()
    is_reseller = user_data and user_data[0] == "reseller"

    # Fetch diamonds from the database
    cursor.execute("SELECT productname, price, reseller_price FROM products WHERE productname LIKE '%[Diamond]%'")
    products = cursor.fetchall()
    conn.close()

    # Check if there are any diamond products
    if not products:
        await update.message.reply_text("No diamond products available at the moment.")
        return

    # Format the diamond product list for display
    product_message = "Available Diamonds:\n"
    for productname, price, reseller_price in products:
        display_price = reseller_price if is_reseller else price
        product_message += f"💎 {productname.replace(' [Diamond]', '')}: ₹ {display_price:.2f}\n"

    await update.message.reply_text(product_message)

async def show_weekly_pass_command(update: Update, context: CallbackContext) -> None:
    """
    Fetch and display the available weekly pass products from the database.
    """
    # Get the user's Telegram ID
    user_id = str(update.effective_user.id)

    # Check if the user is a reseller
    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM users WHERE userid = ?", (user_id,))
    user_data = cursor.fetchone()
    is_reseller = user_data and user_data[0] == "reseller"

    # Fetch weekly pass products from the database
    cursor.execute("SELECT productname, price, reseller_price FROM products WHERE productname LIKE '%[Wkp]%'")
    products = cursor.fetchall()
    conn.close()

    # Check if there are any weekly pass products
    if not products:
        await update.message.reply_text("No weekly pass products available at the moment.")
        return

    # Format the weekly pass product list for display
    product_message = "Available Weekly Passes:\n"
    for productname, price, reseller_price in products:
        display_price = reseller_price if is_reseller else price
        product_message += f"💎 {productname.replace(' [Wkp]', '')}: ₹ {display_price:.2f}\n"

    await update.message.reply_text(product_message)

async def show_bonus_command(update: Update, context: CallbackContext) -> None:
    """
    Fetch and display the available bonus products from the database.
    """
    # Get the user's Telegram ID
    user_id = str(update.effective_user.id)

    # Check if the user is a reseller
    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM users WHERE userid = ?", (user_id,))
    user_data = cursor.fetchone()
    is_reseller = user_data and user_data[0] == "reseller"

    # Fetch bonus products from the database
    cursor.execute("SELECT productname, price, reseller_price FROM products WHERE productname LIKE '%[Bonus]%'")
    products = cursor.fetchall()
    conn.close()

    # Check if there are any bonus products
    if not products:
        await update.message.reply_text("No bonus products available at the moment.")
        return

    # Format the bonus product list for display
    product_message = "Available Bonus Products:\n For each level, the Double Diamonds bonus applies only to your first purchase, regardless of the payment channel or platform.\n\n"
    for productname, price, reseller_price in products:
        display_price = reseller_price if is_reseller else price
        product_message += f"🎁 {productname.replace(' [Bonus]', '')}: ₹ {display_price:.2f}\n"

    await update.message.reply_text(product_message)

# User Command: Check Wallet Balance
async def wallet_command(update: Update, context: CallbackContext) -> None:
    """
    Check and display the user's wallet balance.
    """
    # Get the user's Telegram ID
    user_id = str(update.effective_user.id)

    # Fetch the user's wallet balance from the database
    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE userid = ?", (user_id,))
    user_data = cursor.fetchone()
    conn.close()

    if not user_data:
        await update.message.reply_text("User not found. Please register using /start.")
        return

    balance = user_data[0]

    # Display the wallet balance
    await update.message.reply_text(f"Your wallet balance is: ₹{balance:.2f}")

# User Command: Add Funds
async def buy_command(update: Update, context: CallbackContext) -> None:
    """
    Initiates the process of adding funds to the user's wallet.
    """
    # Check if the required arguments are provided
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /buy <amount>")
        return

    # Extract the amount to be added from the command arguments
    try:
        amount = float(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid amount. Please provide a valid number.")
        return

    # Check if the user exists in the database
    user_id = str(update.effective_user.id)
    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE userid = ?", (user_id,))
    user_data = cursor.fetchone()

    if not user_data:
        await update.message.reply_text("User not found. Please register using /start.")
        return

    try:
        if amount <= 0:
            raise ValueError("Amount must be greater than zero.")
    except ValueError:
        await update.message.reply_text("Invalid amount. Please provide a valid number greater than zero.")
        return

    # Generate a random reference number
    reference_number = f"REF-{random.randint(100000, 999999)}"
    user_id = str(update.effective_user.id)

    # Save the payment details to the database with a "PENDING" status
    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO payments (userid, amount, reference, status, timestamp)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, amount, reference_number, "PENDING", time.strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()
    conn.close()

    # Create a QR code instance
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(f"upi://pay?pa={UPI_ID}&pn={BOT_NAME}&am={amount:.2f}&cu=INR&ref={reference_number}")
    qr.make(fit=True)

    # Save the QR code to a BytesIO object
    qr_image = BytesIO()
    qr.make_image(fill="black", back_color="white").save(qr_image)
    qr_image.seek(0)  # Reset the pointer to the beginning of the BytesIO object

    # Notify the user with the QR code and payment details
    try:
        await update.message.reply_photo(
            photo=InputFile(qr_image, filename="payment_qr.png"),
            caption=f"""
💳 Add Funds to Your Wallet

Amount: ₹{amount:.2f}
📝 Payment Reference: {reference_number}
🔐 To verify your payment after completion, use /UTR <utr>

Scan this QR code to pay ₹{amount:.2f} to add funds to your wallet.
UPI ID: `{UPI_ID}`
""",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"Failed to send QR code: {e}")

# User Command: Submit Payment
import requests
import sqlite3
from datetime import datetime, timedelta

# BharatPe API credentials
BHARATPE_MERCHANT_ID = "39271741"
BHARATPE_TOKEN = "caa0fde42822418da23f4d0a7fd4daa9"
BHARATPE_API_URL = "https://payments-tesseract.bharatpe.in/api/v1/merchant/transactions"

async def submit_payment_command(update, context):
    """
    Verify BharatPe payment using UTR and add funds to the user's account.
    """
    # Check if the required arguments are provided
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /UTR <utr>")
        return

    # Extract the UTR (Unique Transaction Reference) from the command arguments
    utr = context.args[0].strip()
    user_id = str(update.effective_user.id)

    if not utr:
        await update.message.reply_text("The UTR cannot be empty.")
        return

    # Check if the UTR is already used
    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM payments WHERE reference = ?", (utr,))
    existing_payment = cursor.fetchone()

    if existing_payment:
        await update.message.reply_text("This UTR is already used.")
        conn.close()
        return

    # Prepare the API request
    from_date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
    to_date = datetime.now().strftime("%Y-%m-%d")
    headers = {
        "token": BHARATPE_TOKEN,
        "user-agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Mobile Safari/537.36",
    }
    params = {
        "module": "PAYMENT_QR",
        "merchantId": BHARATPE_MERCHANT_ID,
        "sDate": from_date,
        "eDate": to_date,
    }

    try:
        # Make the API request
        response = requests.get(BHARATPE_API_URL, headers=headers, params=params)
        response_data = response.json()

        # Filter transactions by UTR
        transactions = response_data.get("data", {}).get("transactions", [])
        matching_transaction = next(
            (txn for txn in transactions if txn.get("bankReferenceNo") == utr), None
        )

        if not matching_transaction:
            await update.message.reply_text("UTR verification failed. Please try again later.")
            conn.close()
            return

        # Verify the transaction details
        if matching_transaction.get("status") == "SUCCESS":
            amount = float(matching_transaction.get("amount", 0.0))

            # Add funds to the user's wallet
            cursor.execute("SELECT balance FROM users WHERE userid = ?", (user_id,))
            user_data = cursor.fetchone()

            if not user_data:
                await update.message.reply_text("User not found. Please register using /start.")
                conn.close()
                return

            current_balance = user_data[0]
            new_balance = current_balance + amount

            # Update the user's wallet balance
            cursor.execute("UPDATE users SET balance = ? WHERE userid = ?", (new_balance, user_id))

            # Insert the payment record
            cursor.execute(
                """
                INSERT INTO payments (userid, amount, reference, status, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, amount, utr, "VERIFIED", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            )
            conn.commit()
            conn.close()

            # Notify the user
            await update.message.reply_text(
                f"Payment verified successfully! ₹{amount:.2f} has been added to your wallet. Current balance: ₹{new_balance:.2f}"
            )
        else:
            await update.message.reply_text("UTR verification failed. Please try again later.")
            conn.close()
    except requests.exceptions.RequestException as e:
        await update.message.reply_text(f"An error occurred while verifying the payment: {e}")
        conn.close()

async def start(update: Update, context: CallbackContext) -> None:
    """
    Handles the /start command. Registers the user if not already registered and displays a welcome message.
    """
    # Get the user's information
    user = update.effective_user
    username = user.username if user.username else user.first_name if user.first_name else "User"
    userid = str(user.id)  # Get the user's Telegram ID

    # Register the user in the database if not already registered
    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()

    # Check if the user is already registered
    cursor.execute("SELECT balance FROM users WHERE userid = ?", (userid,))
    user_data = cursor.fetchone()

    if not user_data:
        # Register the user with a default balance of 0.0
        cursor.execute("""
            INSERT INTO users (userid, username, balance, register_date)
            VALUES (?, ?, ?, ?)
        """, (userid, username, 0.0, time.strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        balance = 0.0  # Default balance for new users
    else:
        balance = user_data[0]  # Fetch the user's current balance

    conn.close()

    # Welcome message
    welcome_message = f"""
🚀 Welcome {username} to {BOT_NAME}!
-------------------------------
🆔 Your Telegram ID: {userid}
💰 Your Current Balance: ₹{balance:.2f}
-------------------------------
- Instant Delivery
- Best Prices
- Secure Payments
- Easy to Use
- Fast Transactions
- 24/7 Support
-------------------------------
✅ User commonds: 
-----------------------
📢 Check available poducts:
	/diamond - Show available Diamonds
	/wkp - Show available Weekly Passes
	/bonus - Show available Bonus Products
------------------------
📢 Add fund & velified Commands:
	/wallet - Check your wallet balance
	/buy <amount> - Add funds to your wallet
	/UTR <reference_number> - Submit payment details after paying to UPI ID
		🧾 UPI ID for payment: {UPI_ID}
------------------------
📢 Order Commands
	/topup <userid> <zoneid> <productname> - Purchase a product
------------------------
❓ /help to see all commands
------------------------

⚠️ Note: Do not share your UPI transaction UTR number with anyone.
If you have any questions, feel free to ask!

☎️ CONTACT {ADMIN_USERNAME}
"""
    await update.message.reply_text(welcome_message)

async def get_id_command(update: Update, context: CallbackContext) -> None:
    """
    Responds with the user's Telegram ID, total spend, current balance, registration date, and role.
    """
    user_id = str(update.effective_user.id)

    # Fetch user details from the database
    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT username, balance, total_spent, register_date, role
        FROM users
        WHERE userid = ?
    """, (user_id,))
    user_data = cursor.fetchone()
    conn.close()

    if not user_data:
        await update.message.reply_text("You are not registered. Please use /start to register.")
        return

    username, balance, total_spent, register_date, role = user_data
    response_message = f"""
Your Account Details:
---------------------------------
🆔 Telegram ID: {user_id}
👤 Username: {username}
💰 Current Balance: ₹{balance:.2f}
📅 Registered On: {register_date}
🔖 Role: {role.capitalize()}
"""
    await update.message.reply_text(response_message)

async def get_role_command(update: Update, context: CallbackContext) -> None:
    """
    Responds with a placeholder message for the user's role.
    """
    user_id = update.effective_user.id
    await update.message.reply_text(f"User ID {user_id}: Role functionality is not implemented yet.")

async def order_history_command(update: Update, context: CallbackContext) -> None:
    """
    Displays the user's order history in the specified format, including MLID and Zone ID.
    """
    user_id = str(update.effective_user.id)

    # Fetch the user's order history from the database
    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT order_id, mlid, zoneid, productname, price, timestamp
            FROM orders
            WHERE user_id = ?
            ORDER BY timestamp DESC
        """, (user_id,))
        orders = cursor.fetchall()
    except sqlite3.Error as e:
        await update.message.reply_text(f"An error occurred while fetching your order history: {e}")
        conn.close()
        return
    finally:
        conn.close()

    # Check if there are any orders
    if not orders:
        await update.message.reply_text("You have no order history.")
        return

    # Format the order history for display
    order_message = "Your Order History:\n"
    for order_id, mlid, zoneid, productname, price, timestamp in orders:
        # Fetch IGN (In-Game Name) using the `fetch_ign` function
        ign = await fetch_ign(order_id, productname)
        order_message += f"""
📜 Order ID: {order_id}
👤 IGN: {ign}
🆔 User ID: {mlid}
🌍 Server ID: {zoneid}
🏷️ Product: {productname}
💸 Price: ₹{price:.2f}
📅 Date: {timestamp}
---
"""
    await update.message.reply_text(order_message)

async def region_command(update: Update, context: CallbackContext) -> None:
    """
    Fetch the Mobile Legends account creation region using the Smile.One API and display it as a country name.
    """
    # Check if the required arguments are provided
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /region <userid> <zoneid>")
        return

    # Extract `userid` and `zoneid` from the command arguments
    userid = context.args[0]
    zoneid = context.args[1]
    product = "mobilelegends"  # Example product type
    request_time = int(time.time())

    # Prepare the parameters for the API request
    params = {
        "email": SMILE_EMAIL,
        "uid": SMILE_UID,
        "userid": userid,
        "zoneid": zoneid,
        "product": product,
        "time": request_time,
    }
    sign = generate_sign(params, SMILE_KEY)
    payload = {**params, "sign": sign}

    # Make the API request to fetch the region
    response = requests.post(ROLE_QUERY_API_URL, data=payload)
    if response.status_code == 200:
        response_data = response.json()
        region_code = response_data.get("region", None)  # Get the region code from the response

        # Map region code to country name
        region_mapping = {
            "US": "United States",
            "IN": "India",
            "PH": "Philippines",
            "ID": "Indonesia",
            "BR": "Brazil",
            "TH": "Thailand",
            "VN": "Vietnam",
            "MY": "Malaysia",
            "SG": "Singapore",
            "JP": "Japan",
            "KR": "South Korea",
            "CN": "China",
            "RU": "Russia",
            "FR": "France",
            "DE": "Germany",
            "UK": "United Kingdom",
            # Add more mappings as needed
        }

        if region_code:
            country_name = region_mapping.get(region_code, "Unknown Region")
            if country_name == "Unknown Region":
                await update.message.reply_text(
                    f"Region for User ID {userid} on Server {zoneid}: {region_code} (Region code not mapped to a country)."
                )
            else:
                await update.message.reply_text(
                    f"Region for User ID {userid} on Server {zoneid}: {country_name}"
                )
        else:
            await update.message.reply_text(
                f"Region for User ID {userid} on Server {zoneid}: Unable to determine region (No region code returned)."
            )
    else:
        await update.message.reply_text(
            f"Error fetching region: {response.status_code}, {response.text}"
        )

async def help_command(update: Update, context: CallbackContext) -> None:
    """
    Displays a list of all available user commands.
    """
    help_message = """
Available Commands:
------------------------------------------
Get your account details:
/getid - Get your Telegram ID, total spend, balance, registration date, and role
/region <userid> <zoneid> - Get the Mobile Legends account creation region
------------------------------------------
Product List Commands:
/diamond - Show available Diamonds
/wkp - Show available Weekly Passes
/bonus - Show available Bonus Products
------------------------------------------
Add Funds and Payment Commands:
/buy <amount> - Add funds to your wallet
/UTR <utr> - Submit payment details for admin verification
/wallet - Check your wallet balance
------------------------------------------
Order Commands:
/orderhistory - View your order history
/topup <ml_id> <serverid> <productname> - Create up to 10 orders for Mobile Legends diamonds
/role <ml_id> <serverid> - Check your Username
"""
    await update.message.reply_text(help_message)

async def view_reseller_products_command(update: Update, context: CallbackContext) -> None:
    """
    Fetch and display products with reseller prices.
    """
    # Get the user's Telegram ID
    user_id = str(update.effective_user.id)

    # Check if the user is a reseller
    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM users WHERE userid = ?", (user_id,))
    user_data = cursor.fetchone()
    if not user_data or user_data[0] != "reseller":
        await update.message.reply_text("Access Denied: You are not authorized to view reseller products. Contact admin {ADMIN_USERNAME}")
        conn.close()
        return

    # Fetch products with reseller prices
    cursor.execute("SELECT productname, reseller_price FROM products WHERE reseller_price > 0")
    products = cursor.fetchall()
    conn.close()

    # Check if there are any products
    if not products:
        await update.message.reply_text("No reseller products available at the moment.")
        return

    # Format the product list for display
    product_message = "Available Reseller Products:\n"
    for productname, reseller_price in products:
        product_message += f"💎 {productname}: ₹ {reseller_price:.2f}\n"

    await update.message.reply_text(product_message)

async def view_reseller_orders_command(update: Update, context: CallbackContext) -> None:
    """
    Fetch and display the reseller's order history.
    """
    # Get the user's Telegram ID
    user_id = str(update.effective_user.id)

    # Check if the user is a reseller
    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM users WHERE userid = ?", (user_id,))
    user_data = cursor.fetchone()
    if not user_data or user_data[0] != "reseller":
        await update.message.reply_text("Access Denied: You are not authorized to view reseller products. Contact admin {ADMIN_USERNAME}")
        conn.close()
        return

    # Fetch the reseller's order history
    cursor.execute("""
        SELECT order_id, mlid, zoneid, productname, price, timestamp
        FROM orders
        WHERE userid = ?
        ORDER BY timestamp DESC
    """, (user_id,))
    orders = cursor.fetchall()
    conn.close()

    # Check if there are any orders
    if not orders:
        await update.message.reply_text("You have no order history.")
        return

    # Format the order history for display
    order_message = "Your Order History:\n"
    for order_id, mlid, zoneid, productname, price, timestamp in orders:
        order_message += f"""
📜 Order ID: {order_id}
🆔 User ID: {mlid}
🌍 Server ID: {zoneid}
🏷️ Product: {productname}
💸 Price: ₹{price:.2f}
📅 Date: {timestamp}
---
"""
    await update.message.reply_text(order_message)

async def fetch_ign(order_id, product_name):
    """
    Fetch the In-Game Name (IGN) using the Smile.One API.
    """
    # Get MLID and Server ID from the order details
    mlid, zoneid = get_order_details(order_id)
    if not mlid or not zoneid:
        return "Unknown (Order details not found)"

    # Get the product ID from the database using the product name
    product_id = get_product_id_by_name(product_name)
    if not product_id:
        return "Unknown (Product not found)"

    # Prepare the API request
    request_time = int(time.time())
    params = {
        "email": SMILE_EMAIL,
        "uid": SMILE_UID,
        "userid": mlid,
        "zoneid": zoneid,
        "product": "mobilelegends",
        "productid": product_id,
        "time": request_time,
    }
    sign = generate_sign(params, SMILE_KEY)
    payload = {**params, "sign": sign}

    # Make the API request
    response = requests.post(ROLE_QUERY_API_URL, data=payload)
    if response.status_code == 200:
        response_data = response.json()
        return response_data.get("username", "Unknown")  # Return the IGN
    else:
        return "Unknown (API error)"

def init_redeem_codes_table():
    """
    Initialize the redeem codes table in the database.
    """
    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS redeem_codes (
            code TEXT PRIMARY KEY,
            value REAL NOT NULL,
            max_uses INTEGER NOT NULL,
            current_uses INTEGER DEFAULT 0,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

# Call the function to ensure the table is initialized
init_redeem_codes_table()

import random

async def generate_code_command(update: Update, context: CallbackContext) -> None:
    """
    Allows the admin to generate redeem codes.
    Usage: /generatecode <value> <max_uses>
    """
    # Check if the user is the admin
    user_id = str(update.effective_user.id)
    if user_id != ADMIN_ID:
        await update.message.reply_text("Access Denied: You are not authorized to generate redeem codes.")
        return

    # Check if the required arguments are provided
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /generatecode <value> <max_uses>")
        return

    try:
        value = float(context.args[0])
        max_uses = int(context.args[1])
        if value <= 0 or max_uses <= 0:
            raise ValueError("Value and max uses must be greater than zero.")
    except ValueError:
        await update.message.reply_text("Invalid value or max uses. Please provide valid numbers.")
        return

    # Generate a 12-digit redeem code in the format 1234-1234-1234
    redeem_code = f"{random.randint(1000, 9999)}-{random.randint(1000, 9999)}-{random.randint(1000, 9999)}"

    # Save the redeem code to the database
    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO redeem_codes (code, value, max_uses, created_by, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (redeem_code, value, max_uses, ADMIN_ID, time.strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

    await update.message.reply_text(f"Redeem code generated successfully!\nCode: {redeem_code}\nValue: ₹{value:.2f}\nMax Uses: {max_uses}")
    
async def redeem_code_command(update: Update, context: CallbackContext) -> None:
    """
    Allows users to redeem a code and add funds to their wallet.
    Usage: /redeem <code>
    """
    # Check if the required arguments are provided
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /redeem <code>")
        return

    redeem_code = context.args[0].strip()
    user_id = str(update.effective_user.id)

    # Fetch the redeem code details from the database
    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    cursor.execute("SELECT value, status FROM redeem_codes WHERE code = ?", (redeem_code,))
    code_data = cursor.fetchone()

    if not code_data:
        await update.message.reply_text("Invalid redeem code. Please check and try again.")
        conn.close()
        return

    value, status = code_data

    if status != "UNUSED":
        await update.message.reply_text("This redeem code has already been used.")
        conn.close()
        return

    # Fetch the user's wallet balance
    cursor.execute("SELECT balance FROM users WHERE userid = ?", (user_id,))
    user_data = cursor.fetchone()

    if not user_data:
        await update.message.reply_text("User not found. Please register using /start.")
        conn.close()
        return

    current_balance = user_data[0]
    new_balance = current_balance + value

    # Update the user's wallet balance
    cursor.execute("UPDATE users SET balance = ? WHERE userid = ?", (new_balance, user_id))

    # Mark the redeem code as used
    cursor.execute("UPDATE redeem_codes SET status = 'USED' WHERE code = ?", (redeem_code,))
    conn.commit()
    conn.close()

    await update.message.reply_text(f"Redeem successful! ₹{value:.2f} has been added to your wallet. Current balance: ₹{new_balance:.2f}")
def add_status_column_to_redeem_codes():
    """
    Add the `status` column to the `redeem_codes` table if it doesn't exist.
    """
    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    try:
        # Add the `status` column if it doesn't exist
        cursor.execute("ALTER TABLE redeem_codes ADD COLUMN status TEXT DEFAULT 'UNUSED'")
        conn.commit()
        print("Column `status` added to the `redeem_codes` table.")
    except sqlite3.OperationalError:
        # Column already exists
        print("Column `status` already exists in the `redeem_codes` table.")
    conn.close()

# Call the function to ensure the column is added
add_status_column_to_redeem_codes()

def recreate_redeem_codes_table():
    """
    Recreate the `redeem_codes` table with the correct schema.
    WARNING: This will delete all existing data in the table.
    """
    conn = sqlite3.connect("wallet.db")
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS redeem_codes")
    cursor.execute("""
        CREATE TABLE redeem_codes (
            code TEXT PRIMARY KEY,
            value REAL NOT NULL,
            max_uses INTEGER NOT NULL,
            current_uses INTEGER DEFAULT 0,
            status TEXT DEFAULT 'UNUSED',
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

# Call the function to recreate the table
# Uncomment the line below to execute it
# recreate_redeem_codes_table()
# Main function to start the bot
def main():
    request = HTTPXRequest(connect_timeout=10, read_timeout=10)  # Set timeouts
    application = Application.builder().token(TELEGRAM_TOKEN).request(request).build()

    # Register commands and handlers 
    application.add_handler(CommandHandler("diamond", show_diamonds_command))  # Show Diamonds
    application.add_handler(CommandHandler("wkp", show_weekly_pass_command))  # Show Weekly Pass
    application.add_handler(CommandHandler("bonus", show_bonus_command))  # Show Bonus Products
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("wallet", wallet_command))
    application.add_handler(CommandHandler("buy", buy_command))
    application.add_handler(CommandHandler("topup", topup_command))  # Replaced /ml with /topup
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("getid", get_id_command))
    application.add_handler(CommandHandler("region", region_command))
    application.add_handler(CommandHandler("wallet", wallet_command))
    application.add_handler(CommandHandler("buy", buy_command))
    application.add_handler(CommandHandler("UTR", submit_payment_command))
    application.add_handler(CommandHandler("orderhistory", order_history_command))
    application.add_handler(CommandHandler("viewusers", view_users_command))
    application.add_handler(CallbackQueryHandler(admin_button_handler))
    application.add_handler(CommandHandler("productlist", product_list_command))
    application.add_handler(CommandHandler("serverlist", server_list_command))
    application.add_handler(CommandHandler("addproduct", add_product_command))
    application.add_handler(CommandHandler("updateprice", update_product_price_command))
    application.add_handler(CommandHandler("changeproduct", change_product_details_command))
    application.add_handler(CommandHandler("removeproduct", remove_product_command))
    application.add_handler(CommandHandler("removeproducts", remove_products_command))
    application.add_handler(CommandHandler("user", user_panel))
    application.add_handler(CommandHandler("reseller", reseller_panel))
    application.add_handler(CommandHandler("role", role_query_command))
    application.add_handler(CommandHandler("purchase", purchase_command))
    application.add_handler(CommandHandler("orderhistory", order_history_command))
    application.add_handler(CommandHandler("viewpayments", view_payments_command))
    application.add_handler(CommandHandler("verifypayment", verify_payment_command))
    application.add_handler(CommandHandler("rejectpayment", reject_payment_command))
    application.add_handler(CallbackQueryHandler(admin_button_handler))
    application.add_handler(CommandHandler("manageproduct", manage_product_command))
    application.add_handler(CommandHandler("fund", fund_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("addresellerprice", add_reseller_price_command))
    application.add_handler(CommandHandler("viewresellerproducts", view_reseller_products_command))
    application.add_handler(CommandHandler("viewresellerorders", view_reseller_orders_command))
    application.add_handler(CommandHandler("addreseller", add_reseller_command))
    application.add_handler(CommandHandler("removereseller", remove_reseller_command))
    application.add_handler(CommandHandler("generatecode", generate_code_command))  # Admin: Generate Redeem Code
    application.add_handler(CommandHandler("redeem", redeem_code_command))  # User: Redeem Code
    # Start the bot
    try:
        application.run_polling()
    except error.Conflict:
        print("Conflict: terminated by another getUpdates request; ensure only one bot instance is running.")
    except error.TimedOut:
        print("Connection timed out. Check your network or proxy settings.")

# Unit tests
class TestSmileOneAPI(unittest.TestCase):

    def test_generate_sign(self):
        params = {
            "time": 1744825223,
        }
        key = "84d312c4e0799bac1d363c87be2e14b7"
        expected_sign = "cc027bb14f8d0a4cdc60ca149a324290"  # Replace with the correct expected value
        generated_sign = generate_sign(params, key)
        self.assertEqual(generated_sign, expected_sign)

if __name__ == "__main__":
    main()
    # Run unit tests
    unittest.main()

