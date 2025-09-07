import os
import time
import json
import io
import sqlite3
from flask import Flask, render_template_string, request, jsonify, make_response, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
import openpyxl
from collections import defaultdict

# تهيئة تطبيق فلاسك
app = Flask(__name__)
# مفتاح سري ضروري لإدارة الجلسات
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'a_very_secret_key_for_brako_app')

# اسم ملف قاعدة البيانات
DATABASE_FILE = 'database.db'
# بيانات اعتماد المسؤول مع كلمة مرور مشفرة
ADMIN_CREDENTIALS = {'username': 'brako', 'password_hash': generate_password_hash('1988')}

def setup_database():
    """
    تقوم بتهيئة قاعدة البيانات وإنشاء الجداول اللازمة إذا لم تكن موجودة بالفعل.
    هذا يضمن عدم فقدان البيانات عند إعادة تشغيل التطبيق.
    """
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    
    # إنشاء جدول جهات الاتصال (للمرسلين والمستلمين)
    c.execute('''
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            phone TEXT,
            country TEXT,
            city TEXT,
            address TEXT
        )
    ''')

    # إنشاء جدول الشحنات مع مفاتيح خارجية لجهات الاتصال
    c.execute('''
        CREATE TABLE IF NOT EXISTS shipments (
            id INTEGER PRIMARY KEY,
            shipmentNumber TEXT,
            invoiceNumber TEXT,
            date TEXT,
            time TEXT,
            branch TEXT,
            shippingType TEXT,
            sender_id INTEGER,
            receiver_id INTEGER,
            paymentMethod TEXT,
            insurance INTEGER,
            insuranceCost REAL,
            packaging INTEGER,
            packagingCost REAL,
            quantity INTEGER,
            unitPrice REAL,
            weight REAL,
            itemType TEXT,
            contents TEXT,
            finalPrice REAL,
            currency TEXT,
            status TEXT,
            trackingCode TEXT,
            FOREIGN KEY (sender_id) REFERENCES contacts (id),
            FOREIGN KEY (receiver_id) REFERENCES contacts (id)
        )
    ''')
    
    # إنشاء جدول سجل الحالات
    c.execute('''
        CREATE TABLE IF NOT EXISTS status_updates (
            id INTEGER PRIMARY KEY,
            shipment_id INTEGER,
            status TEXT,
            city TEXT,
            notes TEXT,
            date TEXT,
            time TEXT,
            FOREIGN KEY (shipment_id) REFERENCES shipments (id)
        )
    ''')

    conn.commit()
    conn.close()

def get_db_connection():
    """ينشئ اتصالاً بقاعدة البيانات ويعيده."""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def admin_required(func):
    """ديكوراتور لحماية مسارات الإدارة."""
    def wrapper(*args, **kwargs):
        if session.get('logged_in'):
            return func(*args, **kwargs)
        return jsonify({"error": "Unauthorized"}), 401
    wrapper.__name__ = func.__name__
    return wrapper

@app.route('/')
def home():
    """يعرض صفحة HTML الرئيسية."""
    return render_template_string(HTML_CONTENT)

@app.route('/api/login', methods=['POST'])
def login():
    """يتعامل مع تسجيل دخول المسؤول ويقوم بتعيين ملف تعريف ارتباط للجلسة."""
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if username == ADMIN_CREDENTIALS['username'] and check_password_hash(ADMIN_CREDENTIALS['password_hash'], password):
        session['logged_in'] = True
        return jsonify({"success": True}), 200
    else:
        return jsonify({"success": False, "message": "Invalid credentials"}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    """يمسح الجلسة عند تسجيل الخروج."""
    session.pop('logged_in', None)
    return jsonify({"success": True}), 200

@app.route('/api/auth_status', methods=['GET'])
def auth_status():
    """يتحقق من حالة مصادقة المسؤول."""
    return jsonify({"isAuthenticated": session.get('logged_in', False)}), 200

@app.route('/api/shipments', methods=['GET', 'POST'])
@admin_required
def handle_shipments():
    """يتعامل مع إنشاء واسترداد الشحنات."""
    conn = get_db_connection()
    c = conn.cursor()
    
    if request.method == 'POST':
        new_shipment = request.json
        
        # إدراج بيانات المرسل والمستلم في جدول جهات الاتصال
        c.execute('INSERT INTO contacts (name, phone, country, city, address) VALUES (?, ?, ?, ?, ?)',
                  (new_shipment['sender']['name'], new_shipment['sender']['phone'], new_shipment['sender']['country'], new_shipment['sender']['city'], new_shipment['sender']['address']))
        sender_id = c.lastrowid
        
        c.execute('INSERT INTO contacts (name, phone, country, city, address) VALUES (?, ?, ?, ?, ?)',
                  (new_shipment['receiver']['name'], new_shipment['receiver']['phone'], new_shipment['receiver']['country'], new_shipment['receiver']['city'], new_shipment['receiver']['address']))
        receiver_id = c.lastrowid
        
        # إنشاء كود التتبع
        branch_prefix = "TOP" if new_shipment.get('branch') == 'topeka' else "BRA"
        tracking_code = branch_prefix + str(int(time.time() * 1000))[-8:]
        
        # إدراج بيانات الشحنة الرئيسية
        c.execute('''
            INSERT INTO shipments (
                shipmentNumber, invoiceNumber, date, time, branch, shippingType,
                sender_id, receiver_id, paymentMethod, insurance, insuranceCost, packaging,
                packagingCost, quantity, unitPrice, weight, itemType, contents,
                finalPrice, currency, status, trackingCode
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            new_shipment['shipmentNumber'], new_shipment['invoiceNumber'],
            new_shipment['date'], new_shipment['time'], new_shipment['branch'],
            new_shipment['shippingType'], sender_id, receiver_id, new_shipment['paymentMethod'],
            new_shipment['insurance'], new_shipment['insuranceCost'],
            new_shipment['packaging'], new_shipment['packagingCost'],
            new_shipment['quantity'], new_shipment['unitPrice'],
            new_shipment['weight'], new_shipment['itemType'], new_shipment['contents'],
            new_shipment['finalPrice'], new_shipment['currency'],
            new_shipment['status'], tracking_code
        ))
        shipment_id = c.lastrowid
        
        # إدراج تحديث الحالة الأولي
        initial_status = new_shipment['statusHistory'][0]
        c.execute('INSERT INTO status_updates (shipment_id, status, city, notes, date, time) VALUES (?, ?, ?, ?, ?, ?)',
                  (shipment_id, initial_status['status'], initial_status['city'], initial_status['notes'], initial_status['date'], initial_status['time']))

        conn.commit()
        conn.close()
        
        # إرجاع تفاصيل الشحنة التي تم إنشاؤها حديثًا
        new_shipment['id'] = shipment_id
        new_shipment['trackingCode'] = tracking_code
        return jsonify(new_shipment), 201
    
    # طلب GET
    c.execute('''
        SELECT 
            s.*,
            sender.name AS sender_name, sender.phone AS sender_phone, sender.country AS sender_country, sender.city AS sender_city, sender.address AS sender_address,
            receiver.name AS receiver_name, receiver.phone AS receiver_phone, receiver.country AS receiver_country, receiver.city AS receiver_city, receiver.address AS receiver_address
        FROM shipments s
        JOIN contacts sender ON s.sender_id = sender.id
        JOIN contacts receiver ON s.receiver_id = receiver.id
        ORDER BY s.id DESC
    ''')
    shipments = c.fetchall()
    
    shipments_list = []
    for s in shipments:
        s_dict = dict(s)
        s_dict['sender'] = {'name': s_dict['sender_name'], 'phone': s_dict['sender_phone'], 'country': s_dict['sender_country'], 'city': s_dict['sender_city'], 'address': s_dict['sender_address']}
        s_dict['receiver'] = {'name': s_dict['receiver_name'], 'phone': s_dict['receiver_phone'], 'country': s_dict['receiver_country'], 'city': s_dict['receiver_city'], 'address': s_dict['receiver_address']}
        
        c.execute('SELECT status, city, notes, date, time FROM status_updates WHERE shipment_id = ? ORDER BY id', (s_dict['id'],))
        s_dict['statusHistory'] = [dict(row) for row in c.fetchall()]
        
        shipments_list.append(s_dict)
    
    conn.close()
    return jsonify(shipments_list)

@app.route('/api/shipments/<int:shipment_id>', methods=['GET', 'DELETE', 'PUT'])
@admin_required
def update_or_delete_shipment(shipment_id):
    """يتعامل مع تحديث وحذف الشحنات بواسطة المعرّف."""
    conn = get_db_connection()
    c = conn.cursor()
    
    if request.method == 'GET':
        c.execute('''
            SELECT 
                s.*,
                sender.name AS sender_name, sender.phone AS sender_phone, sender.country AS sender_country, sender.city AS sender_city, sender.address AS sender_address,
                receiver.name AS receiver_name, receiver.phone AS receiver_phone, receiver.country AS receiver_country, receiver.city AS receiver_city, receiver.address AS receiver_address
            FROM shipments s
            JOIN contacts sender ON s.sender_id = sender.id
            JOIN contacts receiver ON s.receiver_id = receiver.id
            WHERE s.id = ?
        ''', (shipment_id,))
        shipment = c.fetchone()
        
        if shipment:
            shipment_dict = dict(shipment)
            shipment_dict['sender'] = {'name': shipment_dict['sender_name'], 'phone': shipment_dict['sender_phone'], 'country': shipment_dict['sender_country'], 'city': shipment_dict['sender_city'], 'address': shipment_dict['sender_address']}
            shipment_dict['receiver'] = {'name': shipment_dict['receiver_name'], 'phone': shipment_dict['receiver_phone'], 'country': shipment_dict['receiver_country'], 'city': shipment_dict['receiver_city'], 'address': shipment_dict['receiver_address']}
            
            c.execute('SELECT status, city, notes, date, time FROM status_updates WHERE shipment_id = ? ORDER BY id', (shipment_dict['id'],))
            shipment_dict['statusHistory'] = [dict(row) for row in c.fetchall()]

            conn.close()
            return jsonify(shipment_dict), 200
        else:
            conn.close()
            return jsonify({"error": "Shipment not found"}), 404

    if request.method == 'DELETE':
        # الحصول على معرّفات جهات الاتصال قبل حذف الشحنة
        c.execute('SELECT sender_id, receiver_id FROM shipments WHERE id = ?', (shipment_id,))
        contact_ids = c.fetchone()
        
        if contact_ids:
            sender_id, receiver_id = contact_ids['sender_id'], contact_ids['receiver_id']
            c.execute('DELETE FROM status_updates WHERE shipment_id = ?', (shipment_id,))
            c.execute('DELETE FROM shipments WHERE id = ?', (shipment_id,))
            c.execute('DELETE FROM contacts WHERE id IN (?, ?)', (sender_id, receiver_id))
            conn.commit()
            conn.close()
            return '', 204
        else:
            conn.close()
            return jsonify({"error": "Shipment not found"}), 404

    if request.method == 'PUT':
        updated_shipment = request.json
        c.execute('SELECT * FROM shipments WHERE id = ?', (shipment_id,))
        existing_shipment = c.fetchone()

        if existing_shipment:
            # تحديث جهات اتصال المرسل والمستلم
            c.execute('UPDATE contacts SET name=?, phone=?, country=?, city=?, address=? WHERE id=?',
                      (updated_shipment['sender']['name'], updated_shipment['sender']['phone'], updated_shipment['sender']['country'], updated_shipment['sender']['city'], updated_shipment['sender']['address'], existing_shipment['sender_id']))
            c.execute('UPDATE contacts SET name=?, phone=?, country=?, city=?, address=? WHERE id=?',
                      (updated_shipment['receiver']['name'], updated_shipment['receiver']['phone'], updated_shipment['receiver']['country'], updated_shipment['receiver']['city'], updated_shipment['receiver']['address'], existing_shipment['receiver_id']))

            # تحديث بيانات الشحنة الرئيسية
            c.execute('''
                UPDATE shipments SET
                    shipmentNumber=?, invoiceNumber=?, date=?, time=?, branch=?, shippingType=?,
                    paymentMethod=?, insurance=?, insuranceCost=?, packaging=?, packagingCost=?,
                    quantity=?, unitPrice=?, weight=?, itemType=?, contents=?, finalPrice=?, currency=?
                WHERE id=?
            ''', (
                updated_shipment['shipmentNumber'], updated_shipment['invoiceNumber'],
                updated_shipment['date'], updated_shipment['time'], updated_shipment['branch'],
                updated_shipment['shippingType'], updated_shipment['paymentMethod'],
                updated_shipment['insurance'], updated_shipment['insuranceCost'],
                updated_shipment['packaging'], updated_shipment['packagingCost'],
                updated_shipment['quantity'], updated_shipment['unitPrice'],
                updated_shipment['weight'], updated_shipment['itemType'], updated_shipment['contents'],
                updated_shipment['finalPrice'], updated_shipment['currency'], shipment_id
            ))
            conn.commit()
            conn.close()
            return jsonify(updated_shipment), 200
    
        conn.close()
        return jsonify({"error": "Shipment not found"}), 404

@app.route('/api/shipments/search', methods=['POST'])
def search_shipments():
    """يبحث عن الشحنات بناءً على معايير مختلفة."""
    conn = get_db_connection()
    c = conn.cursor()
    search_term = f"%{request.json.get('query', '').lower()}%"
    
    c.execute('''
        SELECT 
            s.*,
            sender.name AS sender_name, sender.phone AS sender_phone, sender.country AS sender_country, sender.city AS sender_city, sender.address AS sender_address,
            receiver.name AS receiver_name, receiver.phone AS receiver_phone, receiver.country AS receiver_country, receiver.city AS receiver_city, receiver.address AS receiver_address
        FROM shipments s
        JOIN contacts sender ON s.sender_id = sender.id
        JOIN contacts receiver ON s.receiver_id = receiver.id
        WHERE
            lower(s.shipmentNumber) LIKE ? OR
            lower(s.invoiceNumber) LIKE ? OR
            lower(s.trackingCode) LIKE ?
        ORDER BY s.id DESC
    ''', (search_term, search_term, search_term))
    
    shipments = c.fetchall()
    
    shipments_list = []
    for s in shipments:
        s_dict = dict(s)
        s_dict['sender'] = {'name': s_dict['sender_name'], 'phone': s_dict['sender_phone'], 'country': s_dict['sender_country'], 'city': s_dict['sender_city'], 'address': s_dict['sender_address']}
        s_dict['receiver'] = {'name': s_dict['receiver_name'], 'phone': s_dict['receiver_phone'], 'country': s_dict['receiver_country'], 'city': s_dict['receiver_city'], 'address': s_dict['receiver_address']}
        
        c.execute('SELECT status, city, notes, date, time FROM status_updates WHERE shipment_id = ? ORDER BY id', (s_dict['id'],))
        s_dict['statusHistory'] = [dict(row) for row in c.fetchall()]
        
        shipments_list.append(s_dict)
    
    conn.close()
    return jsonify(shipments_list)

@app.route('/api/shipments/update_status', methods=['POST'])
@admin_required
def update_status():
    """يحدث حالة شحنات متعددة."""
    data = request.json
    selected_ids = data.get('selectedIds', [])
    new_status = data.get('newStatus')
    current_city = data.get('currentCity')
    status_notes = data.get('statusNotes')
    
    conn = get_db_connection()
    c = conn.cursor()

    for shipment_id in selected_ids:
        c.execute('UPDATE shipments SET status = ? WHERE id = ?', (new_status, shipment_id))
        
        c.execute('INSERT INTO status_updates (shipment_id, status, city, notes, date, time) VALUES (?, ?, ?, ?, ?, ?)',
                  (shipment_id, new_status, current_city, status_notes, data.get('date'), data.get('time')))
    
    conn.commit()
    conn.close()
    return jsonify({'message': 'Status updated successfully'})
    
@app.route('/api/shipments/export_excel', methods=['POST'])
@admin_required
def export_excel():
    """يولد ملف Excel من الشحنات المحددة ويعيده."""
    data = request.json
    shipments_to_export = data.get('shipments', [])

    if not shipments_to_export:
        return jsonify({"error": "No shipments provided to export"}), 400

    try:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Shipments Report"
        
        headers = [
            "رقم الشحنة", "كود التتبع", "المرسل", "هاتف المرسل", "دولة المرسل", "مدينة المرسل",
            "المستلم", "هاتف المستلم", "دولة المستلم", "مدينة المستلم",
            "العدد", "الوزن (كغ)", "النوع", "المحتويات", "السعر الأساسي", "تكلفة التأمين",
            "تكلفة التغليف", "السعر النهائي", "العملة", "طريقة الدفع", "الحالة"
        ]
        ws.append(headers)
        
        for shipment in shipments_to_export:
            weight = float(shipment.get('weight', 0))
            unit_price = float(shipment.get('unitPrice', 0))
            insurance_cost = float(shipment.get('insuranceCost', 0))
            packaging_cost = float(shipment.get('packagingCost', 0))
            
            # حساب السعر الأساسي بناءً على الوزن، مع فرض 10 كغ كحد أدنى
            calculated_weight = max(weight, 10)
            base_price = calculated_weight * unit_price

            row_data = [
                str(shipment.get('shipmentNumber', '')),
                str(shipment.get('trackingCode', '')),
                str(shipment.get('sender', {}).get('name', '')),
                str(shipment.get('sender', {}).get('phone', '')),
                str(shipment.get('sender', {}).get('country', '')),
                str(shipment.get('sender', {}).get('city', '')),
                str(shipment.get('receiver', {}).get('name', '')),
                str(shipment.get('receiver', {}).get('phone', '')),
                str(shipment.get('receiver', {}).get('country', '')),
                str(shipment.get('receiver', {}).get('city', '')),
                str(shipment.get('quantity', '')),
                str(shipment.get('weight', '')),
                str(shipment.get('itemType', '')),
                str(shipment.get('contents', '')),
                f"{base_price:.2f}",
                f"{insurance_cost:.2f}",
                f"{packaging_cost:.2f}",
                str(shipment.get('finalPrice', '')),
                str(shipment.get('currency', '')),
                str("دفع مقدم" if shipment.get('paymentMethod') == 'prepaid' else "دفع عكسي"),
                str(shipment.get('status', ''))
            ]
            ws.append(row_data)

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        response.headers['Content-Disposition'] = 'attachment; filename=shipment_report.xlsx'
        
        return response
    except Exception as e:
        print(f"Error generating Excel file: {e}")
        return jsonify({"error": "Failed to generate Excel file"}), 500
        
@app.route('/api/shipments/generate_a4_print_html', methods=['POST'])
@admin_required
def generate_a4_print_html():
    """يولد صفحة HTML مع فواتير مصممة لصفحات A4 نصفية."""
    data = request.json
    shipments_to_print = data.get('shipments', [])

    if not shipments_to_print:
        return jsonify({"error": "No shipments provided to print"}), 400

    A4_HALF_PRINT_TEMPLATE = """
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <title>فواتير الشحنات</title>
        <style>
            @font-face {
                font-family: 'Cairo';
                src: url('https://fonts.gstatic.com/s/cairo/v15/SLXAc1nobb-F_Jt1CgB3H.ttf') format('truetype');
                font-weight: 400;
                font-style: normal;
            }
            
            body { font-family: 'Cairo', sans-serif; margin: 0; padding: 0; font-size: 10px; }
            
            @page {
                size: A4 portrait;
                margin: 0;
            }
            
            .page-container {
                width: 210mm; /* A4 width */
                height: 297mm; /* A4 height */
                page-break-after: always;
                box-sizing: border-box;
                padding: 10mm;
            }
            
            .invoice-half-a4 {
                width: 100%;
                height: 148.5mm; /* Half of A4 height */
                border: 1px dashed #999;
                padding: 10px;
                box-sizing: border-box;
                page-break-inside: avoid;
                margin-bottom: 5mm;
                display: flex;
                flex-direction: column;
                justify-content: space-between;
            }

            .header { text-align: center; margin-bottom: 5px; padding-bottom: 5px; border-bottom: 1px solid #000; }
            .company-name { font-size: 16px; font-weight: bold; color: #1e40af; }
            .invoice-title { font-size: 12px; color: #14b8a6; }
            .tracking-code { background: #fbbf24; color: #1e40af; padding: 3px; border-radius: 3px; font-weight: bold; text-align: center; margin-top: 5px; font-size: 10px; }
            .section-title { font-size: 12px; font-weight: bold; color: #1e40af; margin-bottom: 5px; border-bottom: 1px solid #1e40af; padding-bottom: 3px; }
            .info-row { font-size: 10px; margin-bottom: 2px; }
            .label { font-weight: bold; color: #374151; }
            .value { color: #1f2937; }
            .grid-print { display: grid; grid-template-columns: 1fr 1fr; gap: 5px; }
            .total-section { background: linear-gradient(135deg, #1e40af, #14b8a6); color: white; padding: 5px; border-radius: 3px; text-align: center; margin-top: 10px; }
            .total-price { font-size: 14px; font-weight: bold; }
            .footer { text-align: center; margin-top: 10px; font-size: 8px; color: #6b7280; }
        </style>
    </head>
    <body>
        <div class="page-container">
        {% for shipment in shipments %}
            <div class="invoice-half-a4">
                <div class="content">
                    <div class="header">
                        <div class="company-name">BRAKO - شركة الشحن الدولي</div>
                        <div class="invoice-title">فاتورة شحنة</div>
                        <div style="margin-top: 5px;">
                            <strong>رقم الشحنة:</strong> {{ shipment.shipmentNumber }} | 
                            <strong>رقم الفاتورة:</strong> {{ shipment.invoiceNumber | default('غير محدد') }}
                        </div>
                        <div class="tracking-code">كود التتبع: {{ shipment.trackingCode }}</div>
                    </div>
                    
                    <div class="grid-print">
                        <div class="info-section">
                            <div class="section-title">معلومات المرسل</div>
                            <div class="info-row"><span class="label">الاسم:</span> <span class="value">{{ shipment.sender.name }}</span></div>
                            <div class="info-row"><span class="label">الهاتف:</span> <span class="value">{{ shipment.sender.phone }}</span></div>
                            <div class="info-row"><span class="label">الدولة:</span> <span class="value">{{ shipment.sender.country }}</span></div>
                            <div class="info-row"><span class="label">المدينة:</span> <span class="value">{{ shipment.sender.city | default('غير محدد') }}</span></div>
                        </div>
                        
                        <div class="info-section">
                            <div class="section-title">معلومات المستلم</div>
                            <div class="info-row"><span class="label">الاسم:</span> <span class="value">{{ shipment.receiver.name }}</span></div>
                            <div class="info-row"><span class="label">الهاتف:</span> <span class="value">{{ shipment.receiver.phone }}</span></div>
                            <div class="info-row"><span class="label">الدولة:</span> <span class="value">{{ shipment.receiver.country }}</span></div>
                            <div class="info-row"><span class="label">المدينة:</span> <span class="value">{{ shipment.receiver.city | default('غير محدد') }}</span></div>
                        </div>
                    </div>
                    
                    <div class="info-section">
                        <div class="section-title">تفاصيل الطرد</div>
                        <div class="info-row"><span class="label">الوزن:</span> <span class="value">{{ shipment.weight }} كغ</span></div>
                        <div class="info-row"><span class="label">العدد:</span> <span class="value">{{ shipment.quantity }}</span></div>
                        <div class="info-row"><span class="label">السعر الإفرادي:</span> <span class="value">{{ shipment.unitPrice }} {{ shipment.currency }}</span></div>
                        <div class="info-row"><span class="label">طريقة الدفع:</span> <span class="value">{{ 'دفع مقدم' if shipment.paymentMethod == 'prepaid' else 'دفع عكسي' }}</span></div>
                    </div>
                    
                    <div class="total-section">
                        <div class="total-price">السعر النهائي: {{ shipment.finalPrice }} {{ shipment.currency }}</div>
                    </div>
                </div>
                
                <div class="footer">
                    <p><strong>شركة BRAKO للشحن الدولي</strong></p>
                    <p>القامشلي: +963943396345 | +963984487359</p>
                    <p>أربيل: +964750123456 | +964751987654</p>
                </div>
            </div>
        {% endfor %}
        </div>
    </body>
    </html>
    """
    
    # حساب الأسعار لكل شحنة
    for shipment in shipments_to_print:
        try:
            weight = float(shipment.get('weight', 0))
            unit_price = float(shipment.get('unitPrice', 0))
            insurance_cost = float(shipment.get('insuranceCost', 0))
            packaging_cost = float(shipment.get('packagingCost', 0))
            
            # حساب السعر الأساسي بناءً على الوزن، مع فرض 10 كغ كحد أدنى
            calculated_weight = max(weight, 10)
            base_price = calculated_weight * unit_price

            shipment['basePrice'] = "{:.2f}".format(base_price)
            shipment['insuranceCost'] = "{:.2f}".format(insurance_cost)
            shipment['packagingCost'] = "{:.2f}".format(packaging_cost)
        except (ValueError, TypeError):
            shipment['basePrice'] = "0.00"
            shipment['insuranceCost'] = "0.00"
            shipment['packagingCost'] = "0.00"
            
    html = render_template_string(A4_HALF_PRINT_TEMPLATE, shipments=shipments_to_print)
    response = make_response(html)
    response.headers['Content-Type'] = 'text/html'
    return response

# قالب HTML مع CSS و JavaScript مدمجة
HTML_CONTENT = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BRAKO - شركة الشحن الدولي</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    colors: {
                        'brako-blue': '#1e40af',
                        'brako-yellow': '#fbbf24',
                        'brako-teal': '#14b8a6',
                        'brako-dark': '#0f172a'
                    },
                    fontFamily: {
                        sans: ['Cairo', 'sans-serif'],
                    },
                },
            },
        };
    </script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@300;400;600;700&display=swap');
        body { font-family: 'Cairo', sans-serif; }
        .gradient-bg { background: linear-gradient(135deg, #1e40af 0%, #14b8a6 50%, #fbbf24 100%); }
        .tab-active { background-color: #1e40af; color: white !important; }
        .tab-inactive { color: #1e40af; background-color: white; }
        .modal { transition: opacity 0.3s ease-in-out; }
        .modal.hidden { opacity: 0; pointer-events: none; }
        .modal-content { transform: scale(0.95); transition: transform 0.3s ease-in-out; }
        .modal:not(.hidden) .modal-content { transform: scale(1); }
        
        .loading-spinner {
            border: 4px solid rgba(255, 255, 255, 0.3);
            border-top: 4px solid #fff;
            border-radius: 50%;
            width: 24px;
            height: 24px;
            animation: spin 1s linear infinite;
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        @media print {
            body { font-size: 10px; margin: 0; padding: 0; }
            .no-print { display: none !important; }
            
            @page {
                size: A4 portrait;
                margin: 0;
            }
            
            .print-page {
                display: flex;
                flex-direction: column;
                justify-content: space-between;
                height: 297mm; /* A4 height */
                width: 210mm; /* A4 width */
                margin: auto;
                padding: 10mm;
                box-sizing: border-box;
                page-break-inside: avoid;
            }
            
            .print-invoice {
                width: 100%;
                height: 148.5mm; /* Half of A4 */
                border: 1px dashed #999;
                padding: 10px;
                box-sizing: border-box;
                page-break-inside: avoid;
                margin-bottom: 5mm;
            }

            .print-header { text-align: center; margin-bottom: 5px; padding-bottom: 5px; border-bottom: 1px solid #000; }
            .company-name { font-size: 16px; font-weight: bold; color: #1e40af; }
            .invoice-title { font-size: 12px; color: #14b8a6; }
            .tracking-code { background: #fbbf24; color: #1e40af; padding: 3px; border-radius: 3px; font-weight: bold; text-align: center; margin-top: 5px; font-size: 10px; }
            .section-title { font-size: 12px; font-weight: bold; color: #1e40af; margin-bottom: 5px; border-bottom: 1px solid #1e40af; padding-bottom: 3px; }
            .info-row { font-size: 10px; margin-bottom: 2px; }
            .label { font-weight: bold; color: #374151; }
            .value { color: #1f2937; }
            .grid-print { display: grid; grid-template-columns: 1fr 1fr; gap: 5px; }
            .total-section { background: linear-gradient(135deg, #1e40af, #14b8a6); color: white; padding: 5px; border-radius: 3px; text-align: center; margin-top: 10px; }
            .total-price { font-size: 14px; font-weight: bold; }
            .footer { text-align: center; margin-top: 10px; font-size: 8px; color: #6b7280; }
        }
    </style>
</head>
<body class="bg-gray-100 font-sans text-brako-dark">
    <div id="modalContainer" class="fixed inset-0 bg-gray-900 bg-opacity-50 flex items-center justify-center p-4 z-50 modal hidden">
        <div class="bg-white rounded-xl shadow-2xl p-6 w-full max-w-sm modal-content">
            <h3 id="modalTitle" class="text-xl font-bold mb-4 text-brako-blue"></h3>
            <p id="modalMessage" class="mb-6 text-gray-700"></p>
            <div id="modalActions" class="flex justify-end gap-3">
                <button id="modalConfirmBtn" class="px-5 py-2 rounded-lg font-semibold bg-brako-blue text-white hover:bg-blue-700 transition-colors hidden">تأكيد</button>
                <button id="modalCancelBtn" class="px-5 py-2 rounded-lg font-semibold bg-gray-200 text-gray-800 hover:bg-gray-300 transition-colors">إلغاء</button>
            </div>
        </div>
    </div>
    
    <div id="postSaveModal" class="fixed inset-0 bg-gray-900 bg-opacity-50 flex items-center justify-center p-4 z-50 modal hidden">
        <div class="bg-white rounded-xl shadow-2xl p-6 w-full max-w-lg modal-content text-center">
            <h3 class="text-2xl font-bold mb-4 text-brako-blue">تم حفظ الشحنة بنجاح!</h3>
            <p class="mb-6 text-gray-700">كود التتبع هو: <span id="savedTrackingCode" class="font-bold text-brako-teal text-xl"></span></p>
            <div class="flex justify-center flex-wrap gap-4 mt-8">
                <button onclick="hidePostSaveModalAndReset()" class="bg-brako-blue text-white px-8 py-3 rounded-full font-semibold hover:bg-blue-700 transition-colors shadow-md">
                    إغلاق و شحنة جديدة
                </button>
                <button onclick="sendWhatsAppFromModal()" class="bg-green-500 text-white px-8 py-3 rounded-full font-semibold hover:bg-green-600 transition-colors shadow-md">
                    📱 إرسال واتساب
                </button>
            </div>
        </div>
    </div>
    
    <div id="printCopiesModal" class="fixed inset-0 bg-gray-900 bg-opacity-50 flex items-center justify-center p-4 z-50 modal hidden">
        <div class="bg-white rounded-xl shadow-2xl p-6 w-full max-w-sm modal-content">
            <h3 class="text-xl font-bold mb-4 text-brako-blue">عدد النسخ</h3>
            <p class="mb-6 text-gray-700">الرجاء تحديد عدد النسخ المراد طباعتها:</p>
            <input type="number" id="copiesCount" class="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brako-blue" value="1" min="1" max="10">
            <div class="flex justify-end gap-3 mt-6">
                <button id="printCopiesBtn" class="px-5 py-2 rounded-lg font-semibold bg-brako-blue text-white hover:bg-blue-700 transition-colors">طباعة</button>
                <button onclick="hidePrintCopiesModal()" class="px-5 py-2 rounded-lg font-semibold bg-gray-200 text-gray-800 hover:bg-gray-300 transition-colors">إلغاء</button>
            </div>
        </div>
    </div>

    <header class="gradient-bg text-white shadow-lg no-print">
        <div class="container mx-auto px-4 py-4">
            <div class="flex items-center justify-between">
                <div class="flex items-center space-x-4 space-x-reverse">
                    <div class="bg-white text-brako-blue px-4 py-2 rounded-lg font-bold text-2xl shadow-md">BRAKO</div>
                    <span class="text-xl font-semibold">شركة الشحن الدولي</span>
                </div>
                <nav class="hidden md:flex space-x-6 space-x-reverse">
                    <a href="#home" class="hover:text-brako-yellow transition-colors cursor-pointer" onclick="showSection('home')">الصفحة الرئيسية</a>
                    <a href="#services" class="hover:text-brako-yellow transition-colors cursor-pointer" onclick="showSection('services')">خدماتنا</a>
                    <a href="#about" class="hover:text-brako-yellow transition-colors cursor-pointer" onclick="showSection('about')">من نحن</a>
                    <a href="#contact" class="hover:text-brako-yellow transition-colors cursor-pointer" onclick="showSection('contact')">تواصل معنا</a>
                    <a href="#tracking" class="hover:text-brako-yellow transition-colors cursor-pointer" onclick="showSection('customerTracking')">تتبع الشحنة</a>
                    <button id="adminButton" onclick="showSection('admin')" class="bg-brako-yellow text-brako-blue px-4 py-2 rounded-lg font-semibold hover:bg-yellow-300 transition-colors shadow-md">إدارة الشحنات</button>
                    <button id="logoutButton" class="hidden bg-red-500 text-white px-4 py-2 rounded-lg font-semibold hover:bg-red-600 transition-colors shadow-md" onclick="handleLogout()">تسجيل الخروج</button>
                </nav>
            </div>
        </div>
    </header>

    <main class="py-8">
        <div id="loadingOverlay" class="fixed inset-0 bg-gray-900 bg-opacity-50 flex items-center justify-center p-4 z-50 hidden">
            <div class="loading-spinner"></div>
        </div>
        
        <section id="home" class="section-content">
            <div class="gradient-bg text-white py-20 shadow-inner">
                <div class="container mx-auto px-4 text-center animate-fadeIn">
                    <h1 class="text-5xl font-bold mb-6 drop-shadow-lg">مرحباً بكم في BRAKO</h1>
                    <p class="text-xl mb-8">شركة الشحن الدولي الرائدة - خدمات شحن موثوقة وسريعة</p>
                    <button onclick="showSection('admin')" class="bg-brako-yellow text-brako-blue px-8 py-4 rounded-full text-lg font-semibold hover:bg-yellow-300 transition-transform transform hover:scale-105 shadow-xl">
                        إدارة الشحنات
                    </button>
                </div>
            </div>
            
            <div class="container mx-auto px-4 py-8">
                <div class="grid md:grid-cols-4 gap-6 mb-12">
                    <div class="bg-white p-6 rounded-lg shadow-lg text-center border-r-4 border-brako-blue transform hover:scale-105 transition-transform">
                        <div class="text-3xl font-bold text-brako-blue mb-2" id="totalShipments">0</div>
                        <p class="text-gray-600">إجمالي الشحنات</p>
                    </div>
                    <div class="bg-white p-6 rounded-lg shadow-lg text-center border-r-4 border-brako-teal transform hover:scale-105 transition-transform">
                        <div class="text-3xl font-bold text-brako-teal mb-2" id="totalRevenue">0</div>
                        <p class="text-gray-600">إجمالي الإيرادات</p>
                    </div>
                    <div class="bg-white p-6 rounded-lg shadow-lg text-center border-r-4 border-green-500 transform hover:scale-105 transition-transform">
                        <div class="text-3xl font-bold text-green-500 mb-2" id="deliveredShipments">0</div>
                        <p class="text-gray-600">الشحنات الجاهزة للاستلام</p>
                    </div>
                    <div class="bg-white p-6 rounded-lg shadow-lg text-center border-r-4 border-brako-yellow transform hover:scale-105 transition-transform">
                        <div class="text-3xl font-bold text-brako-yellow mb-2" id="pendingShipments">0</div>
                        <p class="text-gray-600">الشحنات قيد التنفيذ</p>
                    </div>
                </div>
            </div>

            <div class="container mx-auto px-4 py-16">
                <div class="grid md:grid-cols-3 gap-8">
                    <div class="bg-white p-6 rounded-lg shadow-lg text-center transform hover:scale-105 transition-transform">
                        <div class="bg-brako-blue text-white w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-4 text-2xl shadow-lg">🚚</div>
                        <h3 class="text-xl font-semibold mb-2">شحن سريع</h3>
                        <p class="text-gray-600">خدمات شحن سريعة وموثوقة لجميع أنحاء العالم</p>
                    </div>
                    <div class="bg-white p-6 rounded-lg shadow-lg text-center transform hover:scale-105 transition-transform">
                        <div class="bg-brako-teal text-white w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-4 text-2xl shadow-lg">📦</div>
                        <h3 class="text-xl font-semibold mb-2">تغليف آمن</h3>
                        <p class="text-gray-600">تغليف احترافي يضمن وصول شحنتك بأمان</p>
                    </div>
                    <div class="bg-white p-6 rounded-lg shadow-lg text-center transform hover:scale-105 transition-transform">
                        <div class="bg-brako-yellow text-white w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-4 text-2xl shadow-lg">🛡️</div>
                        <h3 class="text-xl font-semibold mb-2">تأمين شامل</h3>
                        <p class="text-gray-600">خدمات تأمين شاملة لحماية شحناتك</p>
                    </div>
                </div>
            </div>
        </section>

        <section id="services" class="section-content hidden">
            <div class="container mx-auto px-4 py-16">
                <h2 class="text-4xl font-bold text-center mb-12 text-brako-blue">خدماتنا</h2>
                <div class="grid md:grid-cols-2 gap-8">
                    <div class="bg-white p-8 rounded-lg shadow-xl border-r-4 border-brako-teal">
                        <h3 class="text-2xl font-semibold mb-4 text-brako-teal">الشحن الدولي</h3>
                        <ul class="space-y-2 text-gray-700">
                            <li>• شحن جوي سريع</li>
                            <li>• شحن بري للدول المجاورة</li>
                            <li>• خدمات التخليص الجمركي</li>
                        </ul>
                    </div>
                    <div class="bg-white p-8 rounded-lg shadow-xl border-r-4 border-brako-teal">
                        <h3 class="text-2xl font-semibold mb-4 text-brako-teal">خدمات إضافية</h3>
                        <ul class="space-y-2 text-gray-700">
                            <li>• تغليف احترافي</li>
                            <li>• تأمين الشحنات</li>
                            <li>• تتبع الشحنات</li>
                            <li>• التوصيل للمنزل</li>
                        </ul>
                    </div>
                </div>
            </div>
        </section>

        <section id="about" class="section-content hidden">
            <div class="container mx-auto px-4 py-16">
                <h2 class="text-4xl font-bold text-center mb-12 text-brako-blue">من نحن</h2>
                <div class="bg-white p-8 rounded-lg shadow-xl max-w-4xl mx-auto border-t-4 border-brako-yellow">
                    <p class="text-lg text-gray-700 leading-relaxed mb-6">
                        شركة BRAKO للشحن الدولي هي إحدى الشركات الرائدة في مجال الشحن والنقل الدولي. نحن نقدم خدمات شحن موثوقة وسريعة لعملائنا في جميع أنحاء العالم.
                    </p>
                    <p class="text-lg text-gray-700 leading-relaxed mb-6">
                        مع سنوات من الخبرة في هذا المجال، نحن ملتزمون بتقديم أفضل الخدمات وضمان وصول شحناتكم بأمان وفي الوقت المحدد.
                    </p>
                    <div class="grid md:grid-cols-2 gap-8 mt-8">
                        <div>
                            <h3 class="text-xl font-semibold mb-4 text-brako-teal">رؤيتنا</h3>
                            <p class="text-gray-700">أن نكون الشركة الرائدة في مجال الشحن الدولي في المنطقة</p>
                        </div>
                        <div>
                            <h3 class="text-xl font-semibold mb-4 text-brako-teal">مهمتنا</h3>
                            <p class="text-gray-700">تقديم خدمات شحن عالية الجودة بأسعار تنافسية</p>
                        </div>
                    </div>
                </div>
            </div>
        </section>

        <section id="contact" class="section-content hidden">
            <div class="container mx-auto px-4 py-16">
                <h2 class="text-4xl font-bold text-center mb-12 text-brako-blue">تواصل معنا</h2>
                <div class="grid md:grid-cols-2 gap-8">
                    <div class="bg-white p-8 rounded-lg shadow-xl border-r-4 border-brako-blue">
                        <h3 class="text-2xl font-semibold mb-6 text-brako-teal">مكتب القامشلي</h3>
                        <div class="space-y-4 text-gray-700">
                            <div class="flex items-center space-x-3 space-x-reverse">
                                <span class="text-brako-blue text-2xl">📞</span>
                                <span>+963943396345</span>
                            </div>
                            <div class="flex items-center space-x-3 space-x-reverse">
                                <span class="text-brako-blue text-2xl">📞</span>
                                <span>+963984487359</span>
                            </div>
                            <div class="flex items-start space-x-3 space-x-reverse">
                                <span class="text-brako-blue text-2xl">📍</span>
                                <span>القامشلي - شارع العام غرب كازية الفلاحين قبل دوار عفرين</span>
                            </div>
                        </div>
                    </div>
                    <div class="bg-white p-8 rounded-lg shadow-xl border-r-4 border-brako-blue">
                        <h3 class="text-2xl font-semibold mb-6 text-brako-teal">مكتب أربيل</h3>
                        <div class="space-y-4 text-gray-700">
                            <div class="flex items-center space-x-3 space-x-reverse">
                                <span class="text-brako-blue text-2xl">📞</span>
                                <span>+964750123456</span>
                            </div>
                            <div class="flex items-center space-x-3 space-x-reverse">
                                <span class="text-brako-blue text-2xl">📞</span>
                                <span>+964751987654</span>
                            </div>
                            <div class="flex items-start space-x-3 space-x-reverse">
                                <span class="text-brako-blue text-2xl">📍</span>
                                <span>أربيل - هفالان مقابل الأسايش العامة</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </section>

        <section id="admin" class="section-content hidden no-print">
            <div id="adminLoginSection" class="container mx-auto px-4 py-16 max-w-md">
                <div class="bg-white rounded-xl shadow-xl p-8 text-center">
                    <h2 class="text-3xl font-bold text-brako-blue mb-6">تسجيل الدخول للإدارة</h2>
                    <form onsubmit="event.preventDefault(); handleAdminLogin();">
                        <div class="mb-4">
                            <label for="adminUsername" class="block text-sm font-medium mb-2 text-right">اسم المستخدم</label>
                            <input type="text" id="adminUsername" class="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brako-blue" placeholder="اسم المستخدم" required>
                        </div>
                        <div class="mb-6">
                            <label for="adminPassword" class="block text-sm font-medium mb-2 text-right">كلمة المرور</label>
                            <input type="password" id="adminPassword" class="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brako-blue" placeholder="كلمة المرور" required>
                        </div>
                        <button type="submit" class="bg-brako-blue text-white px-8 py-3 rounded-full font-semibold hover:bg-blue-700 transition-colors shadow-md">
                            دخول
                        </button>
                    </form>
                </div>
            </div>
    
            <div id="adminPanelContent" class="hidden">
                <div class="container mx-auto px-4 py-8">
                    <h2 class="text-3xl font-bold text-center mb-8 text-brako-blue">إدارة الشحنات</h2>
                    
                    <div class="flex justify-center mb-8">
                        <div class="bg-white rounded-full p-1 shadow-inner flex space-x-1 space-x-reverse">
                            <button id="addShipmentTab" onclick="showAdminTab('addShipment')" class="px-6 py-3 rounded-full font-semibold transition-colors tab-active">
                                إضافة شحنة جديدة
                            </button>
                            <button id="shipmentsListTab" onclick="showAdminTab('shipmentsList')" class="px-6 py-3 rounded-full font-semibold transition-colors tab-inactive hover:bg-gray-100">
                                قائمة الشحنات
                            </button>
                            <button id="trackingUpdateTab" onclick="showAdminTab('trackingUpdate')" class="px-6 py-3 rounded-full font-semibold transition-colors tab-inactive hover:bg-gray-100">
                                تحديث التتبع
                            </button>
                        </div>
                    </div>

                    <div id="addShipmentSection" class="admin-tab-content">
                        <form class="bg-white rounded-xl shadow-xl p-8 max-w-6xl mx-auto" onsubmit="event.preventDefault(); saveShipment();">
                                <input type="hidden" id="shipmentId" value="">
                                <h3 id="formTitle" class="text-xl font-bold mb-4 text-brako-blue">إضافة شحنة جديدة</h3>
                            <div class="border-2 border-brako-blue rounded-xl p-6 mb-6 shadow-sm">
                                <h3 class="text-xl font-bold mb-4 text-brako-blue">معلومات الشحنة</h3>
                                <div class="grid md:grid-cols-4 gap-4">
                                    <div>
                                        <label class="block text-sm font-medium mb-2">رقم الشحنة</label>
                                        <input type="text" id="shipmentNumber" class="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brako-blue focus:border-transparent transition-shadow" placeholder="رقم الشحنة" required>
                                    </div>
                                    <div>
                                        <label class="block text-sm font-medium mb-2">رقم الفاتورة</label>
                                        <input type="text" id="invoiceNumber" class="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brako-blue focus:border-transparent transition-shadow" placeholder="رقم الفاتورة">
                                    </div>
                                    <div>
                                        <label class="block text-sm font-medium mb-2">التاريخ</label>
                                        <input type="date" id="shipmentDate" class="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brako-blue focus:border-transparent transition-shadow" required>
                                    </div>
                                    <div>
                                        <label class="block text-sm font-medium mb-2">الوقت</label>
                                        <input type="time" id="shipmentTime" class="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brako-blue focus:border-transparent transition-shadow" required>
                                    </div>
                                </div>
                                <div class="mt-4 grid md:grid-cols-2 gap-4">
                                    <div>
                                        <label class="block text-sm font-medium mb-2">الفرع</label>
                                        <select id="branch" class="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brako-blue focus:border-transparent transition-shadow" required>
                                            <option value="">اختر الفرع</option>
                                            <option value="topeka">توبيكا</option>
                                            <option value="brako">براكو</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label class="block text-sm font-medium mb-2">نوع الشحن</label>
                                        <select id="shippingType" class="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brako-blue focus:border-transparent transition-shadow">
                                            <option value="local">محلي</option>
                                            <option value="international">دولي</option>
                                        </select>
                                    </div>
                                </div>
                            </div>

                            <div class="border-2 border-brako-teal rounded-xl p-6 mb-6 shadow-sm">
                                <h3 class="text-xl font-bold mb-4 text-brako-teal">معلومات المرسل والمستلم</h3>
                                <div class="grid md:grid-cols-2 gap-8">
                                    <div>
                                        <h4 class="font-semibold mb-3 text-brako-blue">معلومات المرسل</h4>
                                        <div class="space-y-4">
                                            <input type="text" id="senderName" class="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brako-teal focus:border-transparent transition-shadow" placeholder="اسم المرسل" required>
                                            
                                            <select id="senderCountry" onchange="updateCountryCode('sender')" class="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brako-teal focus:border-transparent transition-shadow" required>
                                                <option value="">اختر الدولة</option>
                                                <option value="syria" data-code="+963">سوريا</option>
                                                <option value="iraq" data-code="+964">العراق</option>
                                                <option value="turkey" data-code="+90">تركيا</option>
                                                <option value="germany" data-code="+49">ألمانيا</option>
                                                <option value="netherlands" data-code="+31">هولندا</option>
                                                <option value="france" data-code="+33">فرنسا</option>
                                                <option value="italy" data-code="+39">إيطاليا</option>
                                                <option value="belgium" data-code="+32">بلجيكا</option>
                                                <option value="spain" data-code="+34">إسبانيا</option>
                                                <option value="greece" data-code="+30">اليونان</option>
                                                <option value="uk" data-code="+44">بريطانيا</option>
                                                <option value="sweden" data-code="+46">السويد</option>
                                                <option value="denmark" data-code="+45">الدنمارك</option>
                                            </select>
                                            
                                            <div class="flex gap-2">
                                                <input type="tel" id="senderPhone" class="flex-1 p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brako-teal focus:border-transparent transition-shadow" placeholder="رقم الهاتف">
                                                <input type="text" id="senderCountryCode" class="w-20 p-3 border border-gray-300 rounded-lg bg-gray-100 text-center font-semibold" readonly placeholder="+00">
                                            </div>

                                            <select id="senderCity" class="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brako-teal focus:border-transparent transition-shadow hidden">
                                                <option value="">اختر المدينة</option>
                                            </select>
                                            
                                            <textarea id="senderAddress" class="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brako-teal focus:border-transparent transition-shadow" rows="3" placeholder="العنوان التفصيلي"></textarea>
                                        </div>
                                    </div>
                                    <div>
                                        <h4 class="font-semibold mb-3 text-brako-blue">معلومات المستلم</h4>
                                        <div class="space-y-4">
                                            <input type="text" id="receiverName" class="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brako-teal focus:border-transparent transition-shadow" placeholder="اسم المستلم" required>
                                            
                                            <select id="receiverCountry" onchange="updateCountryCode('receiver')" class="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brako-teal focus:border-transparent transition-shadow" required>
                                                <option value="">اختر الدولة</option>
                                                <option value="syria" data-code="+963">سوريا</option>
                                                <option value="iraq" data-code="+964">العراق</option>
                                                <option value="turkey" data-code="+90">تركيا</option>
                                                <option value="germany" data-code="+49">ألمانيا</option>
                                                <option value="netherlands" data-code="+31">هولندا</option>
                                                <option value="france" data-code="+33">فرنسا</option>
                                                <option value="italy" data-code="+39">إيطاليا</option>
                                                <option value="belgium" data-code="+32">بلجيكا</option>
                                                <option value="spain" data-code="+34">إسبانيا</option>
                                                <option value="greece" data-code="+30">اليونان</option>
                                                <option value="uk" data-code="+44">بريطانيا</option>
                                                <option value="sweden" data-code="+46">السويد</option>
                                                <option value="denmark" data-code="+45">الدنمارك</option>
                                            </select>
                                            
                                            <div class="flex gap-2">
                                                <input type="tel" id="receiverPhone" class="flex-1 p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brako-teal focus:border-transparent transition-shadow" placeholder="رقم الهاتف">
                                                <input type="text" id="receiverCountryCode" class="w-20 p-3 border border-gray-300 rounded-lg bg-gray-100 text-center font-semibold" readonly placeholder="+00">
                                            </div>
                                            
                                            <select id="receiverCity" class="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brako-teal focus:border-transparent transition-shadow hidden">
                                                <option value="">اختر المدينة</option>
                                            </select>
                                            
                                            <textarea id="receiverAddress" class="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brako-teal focus:border-transparent transition-shadow" rows="3" placeholder="العنوان التفصيلي"></textarea>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <div class="border-2 border-brako-yellow rounded-xl p-6 mb-6 shadow-sm">
                                <h3 class="text-xl font-bold mb-4 text-brako-blue">طريقة الدفع والخدمات الإضافية</h3>
                                <div class="grid md:grid-cols-3 gap-6">
                                    <div>
                                        <label class="block text-sm font-medium mb-2">طريقة الدفع</label>
                                        <select id="paymentMethod" class="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brako-yellow focus:border-transparent transition-shadow">
                                            <option value="prepaid">دفع مقدم</option>
                                            <option value="cod">دفع عكسي</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label class="flex items-center space-x-2 space-x-reverse">
                                            <input type="checkbox" id="insurance" onchange="toggleInsurance()" class="w-5 h-5 text-brako-blue">
                                            <span class="text-sm font-medium">التأمين</span>
                                        </label>
                                        <div id="insuranceDetails" class="mt-2 hidden">
                                            <input type="number" id="insuranceCost" class="w-full p-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brako-yellow" placeholder="تكلفة التأمين" oninput="calculateTotal()">
                                        </div>
                                    </div>
                                    <div>
                                        <label class="flex items-center space-x-2 space-x-reverse">
                                            <input type="checkbox" id="packaging" onchange="togglePackaging()" class="w-5 h-5 text-brako-blue">
                                            <span class="text-sm font-medium">التغليف</span>
                                        </label>
                                        <div id="packagingDetails" class="mt-2 hidden">
                                            <input type="number" id="packagingCost" class="w-full p-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brako-yellow" placeholder="تكلفة التغليف" oninput="calculateTotal()">
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <div class="border-2 border-brako-blue rounded-xl p-6 mb-6 shadow-sm">
                                <h3 class="text-2xl font-bold mb-4 text-brako-blue">تفاصيل الطرد</h3>
                                <div class="grid md:grid-cols-5 gap-4 mb-4">
                                    <div>
                                        <label class="block text-sm font-medium mb-2">العدد</label>
                                        <input type="number" id="quantity" class="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brako-blue focus:border-transparent" placeholder="العدد" oninput="calculateTotal()">
                                    </div>
                                    <div>
                                        <label class="block text-sm font-medium mb-2">السعر الإفرادي</label>
                                        <input type="number" id="unitPrice" class="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brako-blue focus:border-transparent" placeholder="السعر الإفرادي" oninput="calculateTotal()">
                                    </div>
                                    <div>
                                        <label class="block text-sm font-medium mb-2">الوزن (كغ)</label>
                                        <input type="number" id="weight" class="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brako-blue focus:border-transparent" placeholder="الوزن" oninput="calculateTotal()">
                                    </div>
                                    <div>
                                        <label class="block text-sm font-medium mb-2">النوع</label>
                                        <input type="text" id="itemType" class="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brako-blue focus:border-transparent" placeholder="نوع البضاعة">
                                    </div>
                                    <div>
                                        <label class="block text-sm font-medium mb-2">محتويات الطرد</label>
                                        <input type="text" id="contents" class="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brako-blue focus:border-transparent" placeholder="المحتويات">
                                    </div>
                                </div>
                                
                                <div class="bg-gray-50 p-4 rounded-lg">
                                    <div class="grid md:grid-cols-4 gap-4 text-lg mb-4">
                                        <div>
                                            <span class="font-semibold">السعر الأساسي: </span>
                                            <span id="basePrice" class="text-brako-blue font-bold">0.00</span>
                                        </div>
                                        <div>
                                            <span class="font-semibold">التأمين: </span>
                                            <span id="insuranceDisplay" class="text-brako-teal font-bold">0.00</span>
                                        </div>
                                        <div>
                                            <span class="font-semibold">التغليف: </span>
                                            <span id="packagingDisplay" class="text-brako-yellow font-bold">0.00</span>
                                        </div>
                                        <div>
                                            <label class="block text-sm font-medium mb-2">العملة</label>
                                            <select id="currency" onchange="updateCurrencyDisplay()" class="w-full p-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brako-blue">
                                                <option value="USD">دولار أمريكي (USD)</option>
                                                <option value="SYP">ليرة سورية (SYP)</option>
                                                <option value="IQD">دينار عراقي (IQD)</option>
                                            </select>
                                        </div>
                                    </div>
                                    <div class="bg-brako-blue text-white p-3 rounded-lg text-center shadow-md">
                                        <span class="font-semibold">السعر النهائي: </span>
                                        <span id="finalPrice" class="font-bold text-xl">0.00</span>
                                        <span id="currencySymbol" class="font-bold text-xl">USD</span>
                                    </div>
                                </div>
                            </div>

                            <div class="flex justify-center flex-wrap gap-4 mt-8">
                                <button type="submit" id="saveButton" class="bg-brako-blue text-white px-8 py-3 rounded-full font-semibold hover:bg-blue-700 transition-colors shadow-md transform hover:scale-105">
                                    حفظ الشحنة
                                </button>
                            </div>
                        </form>
                    </div>

                    <div id="shipmentsListSection" class="admin-tab-content hidden">
                        <div class="bg-white rounded-xl shadow-xl p-6">
                            <h3 class="text-xl font-bold text-brako-teal mb-6">جميع الشحنات</h3>
                            
                            <div class="mb-6 flex flex-wrap gap-4">
                                <input type="text" id="searchInput" class="flex-1 p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brako-blue" placeholder="البحث برقم الشحنة، رقم الفاتورة، أو كود التتبع">
                                <button onclick="searchAndFilter()" class="bg-brako-blue text-white px-6 py-3 rounded-lg font-semibold hover:bg-blue-700 transition-colors">
                                    بحث
                                </button>
                                <button onclick="clearSearchAndLoad()" class="bg-gray-500 text-white px-6 py-3 rounded-lg font-semibold hover:bg-gray-600 transition-colors">
                                    مسح
                                </button>
                                <button onclick="exportFilteredShipmentsToExcel()" class="bg-brako-teal text-white px-6 py-3 rounded-lg font-semibold hover:bg-teal-700 transition-colors">
                                    تصدير الفواتير (Excel)
                                </button>
                            </div>
                            
                            <div id="shipmentsTable" class="overflow-x-auto rounded-lg shadow-inner">
                                <table class="w-full border-collapse">
                                    <thead>
                                        <tr class="bg-brako-blue text-white text-sm">
                                            <th class="border border-gray-300 p-3"><input type="checkbox" id="selectAllCheckboxes" onclick="toggleAllCheckboxes()" class="w-4 h-4 text-brako-blue rounded-md"></th>
                                            <th class="border border-gray-300 p-3">رقم الشحنة</th>
                                            <th class="border border-gray-300 p-3">كود التتبع</th>
                                            <th class="border border-gray-300 p-3">المرسل</th>
                                            <th class="border border-gray-300 p-3">المستلم</th>
                                            <th class="border border-gray-300 p-3">هاتف المستلم</th>
                                            <th class="border border-gray-300 p-3">العدد</th>
                                            <th class="border border-gray-300 p-3">الوزن</th>
                                            <th class="border border-gray-300 p-3">المبلغ (دفع عكسي)</th>
                                            <th class="border border-gray-300 p-3">الحالة</th>
                                            <th class="border border-gray-300 p-3">الإجراءات</th>
                                        </tr>
                                    </thead>
                                    <tbody id="shipmentsTableBody">
                                        <tr>
                                            <td colspan="11" class="text-center p-8 text-gray-500">لا توجد شحنات مسجلة</td>
                                        </tr>
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>

                    <div id="trackingUpdateSection" class="admin-tab-content hidden">
                        <div class="bg-white rounded-xl shadow-xl p-6">
                            <h3 class="text-xl font-bold text-brako-teal mb-6">تحديث حالات التتبع</h3>
                            
                            <div class="mb-6 flex flex-wrap gap-4">
                                <input type="text" id="trackingSearchInput" class="flex-1 p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brako-blue" placeholder="البحث برقم الشحنة أو رقم الفاتورة">
                                <button onclick="searchForTracking()" class="bg-brako-blue text-white px-6 py-3 rounded-lg font-semibold hover:bg-blue-700 transition-colors">
                                    بحث
                                </button>
                            </div>
                            
                            <div id="trackingResults" class="hidden border-t pt-6 mt-6">
                                <div class="mb-4">
                                    <label class="flex items-center space-x-2 space-x-reverse mb-4">
                                        <input type="checkbox" id="selectAllTracking" onchange="toggleSelectAllTracking()" class="w-5 h-5 text-brako-blue rounded-md">
                                        <span class="font-semibold">تحديد الكل</span>
                                    </label>
                                </div>
                                
                                <div id="trackingShipmentsList" class="mb-6 space-y-3"></div>
                                
                                <div class="grid md:grid-cols-3 gap-4 mb-6">
                                    <div>
                                        <label class="block text-sm font-medium mb-2">الحالة الجديدة</label>
                                        <select id="newStatus" class="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brako-blue">
                                            <option value="in_sorting">قيد الفرز</option>
                                            <option value="local_shipping">شحن داخلي</option>
                                            <option value="departed">انطلاق الشحنة</option>
                                            <option value="at_border">في المعبر</option>
                                            <option value="in_transit">في الطريق</option>
                                            <option value="arrived_city">وصول إلى المدينة</option>
                                            <option value="delayed">مؤجل</option>
                                            <option value="ready_pickup">جاهزة للاستلام</option>
                                            <option value="returned">مرتجع</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label class="block text-sm font-medium mb-2">المدينة الحالية</label>
                                        <select id="currentCity" class="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brako-blue">
                                            <option value="">اختر المدينة</option>
                                            <option value="دمشق">دمشق</option>
                                            <option value="حمص">حمص</option>
                                            <option value="القامشلي">القامشلي</option>
                                            <option value="حلب">حلب</option>
                                            <option value="الرقة">الرقة</option>
                                            <option value="دير الزور">دير الزور</option>
                                            <option value="المالكية">المالكية</option>
                                            <option value="معبدة">معبدة</option>
                                            <option value="الجوادية">الجوادية</option>
                                            <option value="القحطانية">القحطانية</option>
                                            <option value="عامودا">عامودا</option>
                                            <option value="الدرباسية">الدرباسية</option>
                                            <option value="الحسكة">الحسكة</option>
                                            <option value="كوباني">كوباني</option>
                                            <option value="أربيل">أربيل</option>
                                            <option value="دهوك">دهوك</option>
                                            <option value="دوميز">دوميز</option>
                                            <option value="السليمانية">السليمانية</option>
                                            <option value="زاخو">زاخو</option>
                                            <option value="فايدة">فايدة</option>
                                            <option value="كركوك">كركوك</option>
                                            <option value="كويلان">كويلان</option>
                                            <option value="دار شكران">دار شكران</option>
                                            <option value="قوشتبه">قوشتبه</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label class="block text-sm font-medium mb-2">ملاحظات</label>
                                        <input type="text" id="statusNotes" class="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brako-blue" placeholder="ملاحظات إضافية">
                                    </div>
                                </div>
                                
                                <button onclick="updateSelectedStatuses()" class="bg-brako-teal text-white px-8 py-3 rounded-full font-semibold hover:bg-teal-700 transition-colors shadow-md">
                                    تحديث الحالات المحددة
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </section>

        <section id="shipmentDetails" class="section-content hidden">
            <div class="container mx-auto px-4 py-8">
                <div class="bg-white rounded-xl shadow-xl p-8 max-w-4xl mx-auto">
                    <div class="flex justify-between items-center mb-6">
                        <h2 class="text-3xl font-bold text-brako-blue">تفاصيل الشحنة</h2>
                        <button onclick="showSection('admin')" class="bg-gray-500 text-white px-4 py-2 rounded-lg hover:bg-gray-600 transition-colors">
                            العودة
                        </button>
                    </div>
                    
                    <div id="shipmentDetailsContent" class="space-y-6"></div>
                    
                    <div class="flex justify-center flex-wrap space-x-4 space-x-reverse mt-8">
                        <button id="printDetailsBtn" class="bg-brako-teal text-white px-6 py-3 rounded-full font-semibold hover:bg-teal-700 transition-colors shadow-md">
                            🖨️ طباعة الفاتورة (A4)
                        </button>
                        <button id="whatsappDetailsBtn" class="bg-green-500 text-white px-6 py-3 rounded-full font-semibold hover:bg-green-600 transition-colors shadow-md">
                            📱 إرسال واتساب
                        </button>
                        <button id="deleteDetailsBtn" class="bg-red-500 text-white px-6 py-3 rounded-full font-semibold hover:bg-red-600 transition-colors shadow-md">
                            حذف الشحنة
                        </button>
                    </div>
                </div>
            </div>
        </section>

        <section id="customerTracking" class="section-content hidden">
            <div class="gradient-bg text-white py-12 shadow-inner">
                <div class="container mx-auto px-4 text-center">
                    <h1 class="text-4xl font-bold mb-6 drop-shadow-lg">تتبع الشحنة</h1>
                    <p class="text-xl">تابع حالة شحنتك في الوقت الفعلي</p>
                </div>
            </div>
            
            <div class="container mx-auto px-4 py-16">
                <div class="bg-white rounded-xl shadow-xl p-8 max-w-2xl mx-auto">
                    <h3 class="text-2xl font-bold text-brako-blue mb-6 text-center">أدخل كود التتبع</h3>
                    
                    <div class="flex flex-wrap gap-4 mb-8">
                        <input type="text" id="trackingCodeInput" class="flex-1 p-4 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brako-blue text-lg" placeholder="أدخل كود التتبع">
                        <button onclick="trackShipment()" class="bg-brako-blue text-white px-8 py-4 rounded-lg font-semibold hover:bg-blue-700 transition-colors shadow-md">
                            تتبع
                        </button>
                    </div>
                    
                    <div id="trackingResult" class="hidden border-t pt-6 mt-6"></div>
                </div>
            </div>
        </section>
    </main>

    <script>
        const API_BASE_URL = '/api/shipments';
        const sectionIds = ['home', 'services', 'about', 'contact', 'customerTracking', 'admin'];
        let allShipments = [];
        let lastSavedShipment = null;
        let isAuthenticated = false;

        const citiesData = {
            syria: ['دمشق', 'حمص', 'القامشلي', 'حلب', 'الرقة', 'دير الزور', 'المالكية', 'معبدة', 'الجوادية', 'القحطانية', 'عامودا', 'الدرباسية', 'الحسكة', 'كوباني'],
            iraq: ['أربيل', 'دهوك', 'دوميز', 'السليمانية', 'زاخو', 'فايدة', 'كركوك', 'كويلان', 'دار شكران', 'قوشتبه']
        };

        const statusTexts = {
            'received': 'استلام في المركز',
            'in_sorting': 'قيد الفرز',
            'local_shipping': 'شحن داخلي',
            'departed': 'انطلاق الشحنة',
            'at_border': 'في المعبر',
            'in_transit': 'في الطريق',
            'arrived_city': 'وصول إلى المدينة',
            'delayed': 'مؤجل',
            'ready_pickup': 'جاهزة للاستلام',
            'returned': 'مرتجع'
        };
        
        function showLoading() { document.getElementById('loadingOverlay').classList.remove('hidden'); }
        function hideLoading() { document.getElementById('loadingOverlay').classList.add('hidden'); }

        function showModal(title, message, isConfirm = false, onConfirm = null) {
            const modal = document.getElementById('modalContainer');
            document.getElementById('modalTitle').textContent = title;
            document.getElementById('modalMessage').textContent = message;
            
            const confirmBtn = document.getElementById('modalConfirmBtn');
            const cancelBtn = document.getElementById('modalCancelBtn');

            if (isConfirm) {
                confirmBtn.classList.remove('hidden');
                confirmBtn.onclick = () => {
                    if (onConfirm) onConfirm();
                    hideModal();
                };
                cancelBtn.onclick = hideModal;
            } else {
                confirmBtn.classList.add('hidden');
                cancelBtn.onclick = hideModal;
            }
            
            modal.classList.remove('hidden');
        }

        function hideModal() {
            const modal = document.getElementById('modalContainer');
            modal.classList.add('hidden');
        }
        
        function showPostSaveModal(shipmentData) {
            lastSavedShipment = shipmentData;
            document.getElementById('savedTrackingCode').textContent = shipmentData.trackingCode;
            document.getElementById('postSaveModal').classList.remove('hidden');
        }

        function hidePostSaveModal() {
            document.getElementById('postSaveModal').classList.add('hidden');
        }

        function hidePostSaveModalAndReset() {
            hidePostSaveModal();
            resetForm();
            loadAllShipments();
        }
        
        function showPrintCopiesModal(shipments) {
            const modal = document.getElementById('printCopiesModal');
            document.getElementById('copiesCount').value = 1;
            modal.classList.remove('hidden');

            const printBtn = document.getElementById('printCopiesBtn');
            printBtn.onclick = () => {
                const count = parseInt(document.getElementById('copiesCount').value);
                if (count > 0) {
                    const shipmentsToPrint = Array(count).fill(shipments[0]);
                    printToNewWindow(shipmentsToPrint);
                }
                hidePrintCopiesModal();
            };
        }

        function hidePrintCopiesModal() {
            const modal = document.getElementById('printCopiesModal');
            modal.classList.add('hidden');
        }

        function sendWhatsAppFromModal() {
            if (lastSavedShipment) {
                sendWhatsApp(lastSavedShipment);
                hidePostSaveModal();
            }
        }

        function sendWhatsApp(shipmentData) {
            const phoneForLink = shipmentData.sender.phone.replace('+', '').replace(/\s/g, '');
            const trackingLink = `${window.location.origin}/#tracking/${shipmentData.trackingCode}`;

            const senderInfo = `${shipmentData.sender.name}
*الوجهة:* ${shipmentData.sender.city || 'غير محدد'}, ${shipmentData.sender.country}
*العنوان:* ${shipmentData.sender.address || 'غير محدد'}`;

            const message = `🚚 *شركة BRAKO للشحن الدولي* 🚚

✅ *تم إنشاء شحنتكم بنجاح!*

📋 *تفاصيل الشحنة:*
• رقم الشحنة: *${shipmentData.shipmentNumber}*
• كود التتبع: *${shipmentData.trackingCode}*
• المرسل: ${senderInfo}
• المستلم: ${shipmentData.receiver.name}

🔍 *لتتبع شحنتكم عبر الرابط التالي:*
${trackingLink}

📞 *للاستفسار:*
+963943396345
+963984487359

🙏 *شكراً لثقتكم بنا*
نحن نعمل على توصيل شحناتكم بأمان وسرعة`;
            
            const whatsappUrl = `https://wa.me/${phoneForLink}?text=${encodeURIComponent(message)}`;
            window.open(whatsappUrl, '_blank');
        }

        function updateCountryCode(type) {
            const countrySelect = document.getElementById(type + 'Country');
            const countryCodeInput = document.getElementById(type + 'CountryCode');
            const citySelect = document.getElementById(type + 'City');
            
            const selectedOption = countrySelect.options[countrySelect.selectedIndex];
            const countryCode = selectedOption.getAttribute('data-code') || '+00';
            const countryValue = selectedOption.value;
            
            countryCodeInput.value = countryCode;
            
            if (citiesData[countryValue]) {
                citySelect.classList.remove('hidden');
                citySelect.innerHTML = '<option value="">اختر المدينة</option>';
                citiesData[countryValue].forEach(city => {
                    const option = document.createElement('option');
                    option.value = city;
                    option.textContent = city;
                    citySelect.appendChild(option);
                });
            } else {
                citySelect.classList.add('hidden');
                citySelect.innerHTML = '<option value="">اختر المدينة</option>';
            }
        }

        async function showSection(sectionId) {
            const sections = document.querySelectorAll('.section-content');
            sections.forEach(section => section.classList.add('hidden'));

            if (sectionId === 'admin') {
                showLoading();
                const response = await fetch('/api/auth_status');
                hideLoading();
                const data = await response.json();
                isAuthenticated = data.isAuthenticated;

                if (isAuthenticated) {
                    document.getElementById('adminPanelContent').classList.remove('hidden');
                    document.getElementById('adminLoginSection').classList.add('hidden');
                    document.getElementById('logoutButton').classList.remove('hidden');
                    document.getElementById(sectionId).classList.remove('hidden');
                    showAdminTab('addShipment');
                } else {
                    document.getElementById('adminLoginSection').classList.remove('hidden');
                    document.getElementById('adminPanelContent').classList.add('hidden');
                    document.getElementById('logoutButton').classList.add('hidden');
                    document.getElementById(sectionId).classList.remove('hidden');
                }
            } else {
                document.getElementById('logoutButton').classList.add('hidden');
                document.getElementById(sectionId).classList.remove('hidden');
            }
            window.location.hash = sectionId;
        }
        
        async function handleLogout() {
            showLoading();
            const response = await fetch('/api/logout', { method: 'POST' });
            hideLoading();
            if (response.ok) {
                isAuthenticated = false;
                document.getElementById('adminPanelContent').classList.add('hidden');
                document.getElementById('adminLoginSection').classList.add('hidden');
                document.getElementById('logoutButton').classList.add('hidden');
                showSection('home');
            } else {
                showModal('خطأ', 'فشل تسجيل الخروج.');
            }
        }

        function toggleInsurance() {
            const checkbox = document.getElementById('insurance');
            const details = document.getElementById('insuranceDetails');
            if (checkbox.checked) {
                details.classList.remove('hidden');
            } else {
                details.classList.add('hidden');
                document.getElementById('insuranceCost').value = '';
            }
            calculateTotal();
        }

        function togglePackaging() {
            const checkbox = document.getElementById('packaging');
            const details = document.getElementById('packagingDetails');
            if (checkbox.checked) {
                details.classList.remove('hidden');
            } else {
                details.classList.add('hidden');
                document.getElementById('packagingCost').value = '';
            }
            calculateTotal();
        }

        function calculateTotal() {
            const weight = parseFloat(document.getElementById('weight').value) || 0;
            const unitPrice = parseFloat(document.getElementById('unitPrice').value) || 0;
            const insuranceCost = parseFloat(document.getElementById('insuranceCost').value) || 0;
            const packagingCost = parseFloat(document.getElementById('packagingCost').value) || 0;

            // حساب السعر الأساسي بناءً على الوزن، مع فرض 10 كغ كحد أدنى
            let basePrice = 0;
            if (weight > 0) {
                const calculatedWeight = (weight < 10) ? 10 : weight;
                basePrice = calculatedWeight * unitPrice;
            }

            const finalPrice = basePrice + insuranceCost + packagingCost;

            document.getElementById('basePrice').textContent = basePrice.toFixed(2);
            document.getElementById('insuranceDisplay').textContent = insuranceCost.toFixed(2);
            document.getElementById('packagingDisplay').textContent = packagingCost.toFixed(2);
            document.getElementById('finalPrice').textContent = finalPrice.toFixed(2);
        }

        function updateCurrencyDisplay() {
            const currency = document.getElementById('currency').value;
            document.getElementById('currencySymbol').textContent = currency;
            calculateTotal();
        }
        
        function showAdminTab(tabName) {
            const tabs = document.querySelectorAll('.admin-tab-content');
            tabs.forEach(tab => tab.classList.add('hidden'));
            
            const tabButtons = document.querySelectorAll('.p-1 button');
            tabButtons.forEach(btn => btn.classList.replace('tab-active', 'tab-inactive'));
            
            if (tabName === 'addShipment') {
                document.getElementById('addShipmentSection').classList.remove('hidden');
                document.getElementById('addShipmentTab').classList.replace('tab-inactive', 'tab-active');
                resetForm();
            } else if (tabName === 'shipmentsList') {
                document.getElementById('shipmentsListSection').classList.remove('hidden');
                document.getElementById('shipmentsListTab').classList.replace('tab-inactive', 'tab-active');
                loadAllShipments();
            } else if (tabName === 'trackingUpdate') {
                document.getElementById('trackingUpdateSection').classList.remove('hidden');
                document.getElementById('trackingUpdateTab').classList.replace('tab-inactive', 'tab-active');
            }
        }
        
        async function startEditShipment(id) {
            if (!isAuthenticated) {
                showModal('لا يوجد تصريح', 'يجب تسجيل الدخول كمسؤول للوصول إلى هذه الميزة.');
                return;
            }

            showLoading();
            try {
                const response = await fetch(`${API_BASE_URL}/${id}`);
                if (!response.ok) {
                    hideLoading();
                    showModal('خطأ', 'لم يتم العثور على الشحنة.');
                    return;
                }
                const shipment = await response.json();
                
                // الانتقال إلى واجهة إضافة/تعديل الشحنة
                showAdminTab('addShipment');

                // ملء حقول النموذج ببيانات الشحنة
                document.getElementById('shipmentId').value = shipment.id;
                document.getElementById('formTitle').textContent = 'تعديل الشحنة';
                document.getElementById('saveButton').textContent = 'حفظ التعديلات';
                
                // ملء بيانات الشحنة الرئيسية
                document.getElementById('shipmentNumber').value = shipment.shipmentNumber;
                document.getElementById('invoiceNumber').value = shipment.invoiceNumber;
                document.getElementById('shipmentDate').value = shipment.date;
                document.getElementById('shipmentTime').value = shipment.time;
                document.getElementById('branch').value = shipment.branch;
                document.getElementById('shippingType').value = shipment.shippingType;
                
                // ملء معلومات المرسل
                document.getElementById('senderName').value = shipment.sender.name;
                const senderCountryOption = Array.from(document.getElementById('senderCountry').options).find(option => option.textContent === shipment.sender.country);
                if (senderCountryOption) {
                    document.getElementById('senderCountry').value = senderCountryOption.value;
                }
                updateCountryCode('sender'); 
                
                const senderPhoneParts = (shipment.sender.phone || '').split(' ');
                document.getElementById('senderCountryCode').value = senderPhoneParts[0] || '';
                document.getElementById('senderPhone').value = senderPhoneParts.slice(1).join('') || '';
                
                if (shipment.sender.city && document.getElementById('senderCity').options.length > 1) {
                    document.getElementById('senderCity').value = shipment.sender.city;
                }
                document.getElementById('senderAddress').value = shipment.sender.address;
                
                // ملء معلومات المستلم
                document.getElementById('receiverName').value = shipment.receiver.name;
                const receiverCountryOption = Array.from(document.getElementById('receiverCountry').options).find(option => option.textContent === shipment.receiver.country);
                if (receiverCountryOption) {
                    document.getElementById('receiverCountry').value = receiverCountryOption.value;
                }
                updateCountryCode('receiver');
                
                const receiverPhoneParts = (shipment.receiver.phone || '').split(' ');
                document.getElementById('receiverCountryCode').value = receiverPhoneParts[0] || '';
                document.getElementById('receiverPhone').value = receiverPhoneParts.slice(1).join('') || '';

                if (shipment.receiver.city && document.getElementById('receiverCity').options.length > 1) {
                    document.getElementById('receiverCity').value = shipment.receiver.city;
                }
                document.getElementById('receiverAddress').value = shipment.receiver.address;
                
                // ملء تفاصيل الدفع والخدمات الإضافية
                document.getElementById('paymentMethod').value = shipment.paymentMethod;
                document.getElementById('insurance').checked = shipment.insurance == 1;
                toggleInsurance();
                if (document.getElementById('insurance').checked) {
                    document.getElementById('insuranceCost').value = shipment.insuranceCost;
                }
                
                document.getElementById('packaging').checked = shipment.packaging == 1;
                togglePackaging();
                if (document.getElementById('packaging').checked) {
                    document.getElementById('packagingCost').value = shipment.packagingCost;
                }
                
                // ملء تفاصيل الطرد
                document.getElementById('quantity').value = shipment.quantity;
                document.getElementById('unitPrice').value = shipment.unitPrice;
                document.getElementById('weight').value = shipment.weight;
                document.getElementById('itemType').value = shipment.itemType;
                document.getElementById('contents').value = shipment.contents;
                document.getElementById('currency').value = shipment.currency;
                
                calculateTotal();
            } catch (error) {
                console.error("Error fetching shipment details:", error);
                showModal('خطأ', 'حدث خطأ أثناء جلب بيانات الشحنة.');
            } finally {
                hideLoading();
            }
        }
        
        async function searchAndFilter() {
            showLoading();
            const searchTerm = document.getElementById('searchInput').value;
            try {
                const response = await fetch(`${API_BASE_URL}/search`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ query: searchTerm })
                });
                const shipments = await response.json();
                displayShipments(shipments);
            } catch (error) {
                console.error("Error searching shipments:", error);
                showModal('خطأ', 'حدث خطأ أثناء البحث عن الشحنات.');
            } finally {
                hideLoading();
            }
        }

        function clearSearchAndLoad() {
            document.getElementById('searchInput').value = '';
            loadAllShipments();
        }
        
        async function sendWhatsAppForShipment(shipmentId) {
            const shipment = allShipments.find(s => s.id === shipmentId);
            if (shipment) {
                sendWhatsApp(shipment);
            }
        }

        async function searchForTracking() {
            showLoading();
            const searchTerm = document.getElementById('trackingSearchInput').value;
            if (!searchTerm) {
                showModal('بيانات ناقصة', 'يرجى إدخال رقم الشحنة أو رقم الفاتورة');
                hideLoading();
                return;
            }
            
            try {
                const response = await fetch(`${API_BASE_URL}/search`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ query: searchTerm })
                });
                const shipments = await response.json();
                
                if (shipments.length === 0) {
                    showModal('لا توجد نتائج', 'لم يتم العثور على شحنات.');
                    return;
                }
                
                displayTrackingResults(shipments);
            } catch (error) {
                console.error("Error searching for tracking:", error);
                showModal('خطأ', 'حدث خطأ أثناء البحث.');
            } finally {
                hideLoading();
            }
        }

        function displayTrackingResults(shipments) {
            const resultsDiv = document.getElementById('trackingResults');
            const listDiv = document.getElementById('trackingShipmentsList');
            
            listDiv.innerHTML = '';
            
            shipments.forEach(shipment => {
                const div = document.createElement('div');
                div.className = 'bg-gray-50 p-4 rounded-lg mb-3 shadow-sm';
                div.innerHTML = `
                    <label class="flex items-center space-x-3 space-x-reverse">
                        <input type="checkbox" class="tracking-checkbox w-5 h-5 text-brako-blue rounded-md" data-id="${shipment.id}">
                        <div class="flex-1">
                            <div class="font-semibold">رقم الشحنة: ${shipment.shipmentNumber}</div>
                            <div class="text-sm text-gray-600">المرسل: ${shipment.sender.name} - المستلم: ${shipment.receiver.name}</div>
                            <div class="text-sm text-gray-600">الحالة الحالية: <span class="${getStatusColor(shipment.status)} px-2 py-0.5 rounded-full text-xs">${getStatusText(shipment.status || 'received')}</span></div>
                        </div>
                    </label>
                `;
                listDiv.appendChild(div);
            });
            
            resultsDiv.classList.remove('hidden');
        }
        
        function toggleAllCheckboxes() {
            const isChecked = document.getElementById('selectAllCheckboxes').checked;
            document.querySelectorAll('.export-checkbox').forEach(checkbox => {
                checkbox.checked = isChecked;
            });
        }

        function toggleSelectAllTracking() {
            const selectAll = document.getElementById('selectAllTracking');
            const checkboxes = document.querySelectorAll('.tracking-checkbox');
            
            checkboxes.forEach(checkbox => {
                checkbox.checked = selectAll.checked;
            });
        }

        async function updateSelectedStatuses() {
            const checkboxes = document.querySelectorAll('.tracking-checkbox:checked');
            if (checkboxes.length === 0) {
                showModal('تحديد شحنات', 'يرجى تحديد شحنة واحدة على الأقل.');
                return;
            }
            if (!isAuthenticated) {
                showModal('خطأ', 'يجب أن تكون مسؤولًا لتحديث الحالة.');
                return;
            }
            showLoading();
            const selectedIds = Array.from(checkboxes).map(cb => parseInt(cb.getAttribute('data-id')));
            const newStatus = document.getElementById('newStatus').value;
            const currentCity = document.getElementById('currentCity').value;
            const statusNotes = document.getElementById('statusNotes').value;
            
            const now = new Date();
            const payload = {
                selectedIds: selectedIds,
                newStatus: newStatus,
                currentCity: currentCity,
                statusNotes: statusNotes,
                date: now.toISOString().split('T')[0],
                time: now.toTimeString().split(' ')[0].substring(0, 5)
            };

            try {
                const response = await fetch(`${API_BASE_URL}/update_status`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                
                if (response.ok) {
                    showModal('نجاح', 'تم تحديث الحالات بنجاح.');
                    document.getElementById('trackingResults').classList.add('hidden');
                    document.getElementById('trackingSearchInput').value = '';
                    loadAllShipments();
                } else {
                    const error = await response.json();
                    showModal('خطأ', error.error || 'حدث خطأ أثناء التحديث.');
                }
            } catch (error) {
                console.error("Error updating statuses:", error);
                showModal('خطأ', 'حدث خطأ أثناء التحديث.');
            } finally {
                hideLoading();
            }
        }

        function getStatusText(status) {
            return statusTexts[status] || 'غير محدد';
        }
        
        async function trackShipment(trackingCode) {
            showLoading();
            trackingCode = trackingCode || document.getElementById('trackingCodeInput').value;
            if (!trackingCode) {
                showModal('بيانات ناقصة', 'يرجى إدخال كود التتبع');
                hideLoading();
                return;
            }
            
            try {
                const response = await fetch(`${API_BASE_URL}/search`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ query: trackingCode })
                });
                const shipments = await response.json();
                
                const shipment = shipments.find(s => s.trackingCode === trackingCode);
                
                if (!shipment) {
                    showModal('خطأ', 'كود التتبع غير صحيح.');
                    return;
                }
                
                displayTrackingInfo(shipment);
            } catch (error) {
                console.error("Error tracking shipment:", error);
                showModal('خطأ', 'حدث خطأ أثناء تتبع الشحنة.');
            } finally {
                hideLoading();
            }
        }

        function displayTrackingInfo(shipment) {
            const resultDiv = document.getElementById('trackingResult');
            
            const statusHistoryHTML = shipment.statusHistory.length > 0 ? shipment.statusHistory.map(status => `
                <div class="flex items-start mb-4 relative pr-8">
                    <div class="absolute right-0 w-8 h-8 flex items-center justify-center rounded-full bg-brako-blue text-white z-10">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-11a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 10.586V7z" clip-rule="evenodd" />
                        </svg>
                    </div>
                    <div class="flex-1 bg-gray-50 p-4 rounded-lg shadow-sm">
                        <div class="font-bold text-lg text-brako-blue">${getStatusText(status.status)}</div>
                        <div class="text-sm text-gray-600">${status.date} - ${status.time}</div>
                        ${status.city ? `<div class="text-sm text-gray-600">المدينة: ${status.city}</div>` : ''}
                        ${status.notes ? `<div class="text-sm text-gray-600">ملاحظات: ${status.notes}</div>` : ''}
                    </div>
                </div>
            `).join('') : '<div class="text-center text-gray-500 p-4">لا توجد تحديثات للحالة</div>';
            
            resultDiv.innerHTML = `
                <div class="border-t pt-6">
                    <div class="bg-brako-blue text-white p-4 rounded-lg mb-6 shadow-md text-center">
                        <h4 class="text-xl font-semibold mb-2">معلومات الشحنة</h4>
                        <p class="text-2xl font-bold">كود التتبع: ${shipment.trackingCode}</p>
                    </div>
                    
                    <div class="grid md:grid-cols-2 gap-4 mb-6 text-gray-700">
                        <div class="bg-gray-100 p-4 rounded-lg">
                            <strong>المرسل:</strong> ${shipment.sender.name}
                        </div>
                        <div class="bg-gray-100 p-4 rounded-lg">
                            <strong>المستلم:</strong> ${shipment.receiver.name}
                        </div>
                        <div class="bg-gray-100 p-4 rounded-lg">
                            <strong>الوزن:</strong> ${shipment.weight} كغ
                        </div>
                        <div class="bg-gray-100 p-4 rounded-lg">
                            <strong>المحتويات:</strong> ${shipment.contents}
                        </div>
                    </div>

                    <h4 class="text-2xl font-bold text-brako-blue mb-4 text-center mt-8">حالة التتبع</h4>
                    <div class="space-y-6">
                        ${statusHistoryHTML}
                    </div>
                </div>
                `;
            
            resultDiv.classList.remove('hidden');
        }

        async function saveShipment() {
            if (!isAuthenticated) {
                showModal('خطأ', 'يجب أن تكون مسؤولًا لحفظ شحنة.');
                return;
            }
            showLoading();
            const shipmentNumber = document.getElementById('shipmentNumber').value;
            const senderName = document.getElementById('senderName').value;
            const receiverName = document.getElementById('receiverName').value;
            const branch = document.getElementById('branch').value;
            const shipmentId = document.getElementById('shipmentId').value;
            
            if (!shipmentNumber || !senderName || !receiverName || !branch) {
                showModal('بيانات ناقصة', 'يرجى ملء البيانات الأساسية (رقم الشحنة، اسم المرسل، اسم المستلم، والفرع)');
                hideLoading();
                return;
            }
            
            const currency = document.getElementById('currency').value;
            const now = new Date();
            const payload = {
                shipmentNumber: shipmentNumber,
                invoiceNumber: document.getElementById('invoiceNumber').value,
                date: document.getElementById('shipmentDate').value,
                time: document.getElementById('shipmentTime').value,
                branch: branch,
                shippingType: document.getElementById('shippingType').value,
                sender: {
                    name: senderName,
                    phone: document.getElementById('senderCountryCode').value + ' ' + document.getElementById('senderPhone').value,
                    country: document.getElementById('senderCountry').options[document.getElementById('senderCountry').selectedIndex].text,
                    city: document.getElementById('senderCity').value,
                    address: document.getElementById('senderAddress').value
                },
                receiver: {
                    name: receiverName,
                    phone: document.getElementById('receiverCountryCode').value + ' ' + document.getElementById('receiverPhone').value,
                    country: document.getElementById('receiverCountry').options[document.getElementById('receiverCountry').selectedIndex].text,
                    city: document.getElementById('receiverCity').value,
                    address: document.getElementById('receiverAddress').value
                },
                paymentMethod: document.getElementById('paymentMethod').value,
                insurance: document.getElementById('insurance').checked,
                insuranceCost: document.getElementById('insuranceCost').value || '0',
                packaging: document.getElementById('packaging').checked,
                packagingCost: document.getElementById('packagingCost').value || '0',
                quantity: document.getElementById('quantity').value,
                unitPrice: document.getElementById('unitPrice').value,
                weight: document.getElementById('weight').value,
                itemType: document.getElementById('itemType').value,
                contents: document.getElementById('contents').value,
                finalPrice: document.getElementById('finalPrice').textContent,
                currency: currency,
                status: 'received',
                statusHistory: [{
                    status: 'received',
                    city: '',
                    notes: 'تم استلام الشحنة في المركز',
                    date: now.toISOString().split('T')[0],
                    time: now.toTimeString().split(' ')[0].substring(0, 5)
                }]
            };

            try {
                let response;
                if (shipmentId) {
                    payload.id = parseInt(shipmentId);
                    response = await fetch(`${API_BASE_URL}/${shipmentId}`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    });
                } else {
                    response = await fetch(API_BASE_URL, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    });
                }

                if (response.ok) {
                    const savedShipment = await response.json();
                    showPostSaveModal(savedShipment);
                    loadAllShipments();
                } else {
                    const error = await response.json();
                    showModal('خطأ', error.error || 'حدث خطأ أثناء الحفظ.');
                }
            } catch (error) {
                console.error("Error saving shipment:", error);
                showModal('خطأ', 'حدث خطأ أثناء الاتصال بالخادم.');
            } finally {
                hideLoading();
            }
        }
        
        async function exportFilteredShipmentsToExcel() {
            if (!isAuthenticated) {
                showModal('خطأ', 'يجب أن تكون مسؤولًا لتصدير البيانات.');
                return;
            }
            const checkboxes = document.querySelectorAll('.export-checkbox:checked');
            const shipmentsToExport = [];
            
            if (checkboxes.length === 0) {
                showModal('لا توجد شحنات', 'يرجى تحديد شحنة واحدة على الأقل لتصديرها.');
                return;
            }

            checkboxes.forEach(checkbox => {
                const shipmentId = checkbox.getAttribute('data-id');
                const shipment = allShipments.find(s => s.id == shipmentId);
                if (shipment) {
                    shipmentsToExport.push(shipment);
                }
            });

            if (shipmentsToExport.length === 0) {
                showModal('لا توجد شحنات', 'لا توجد شحنات لتصديرها.');
                return;
            }

            showModal('جارٍ التصدير', 'يتم الآن توليد ملف Excel. يرجى الانتظار...', false);
            
            const url = '/api/shipments/export_excel';
            try {
                const response = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ shipments: shipmentsToExport })
                });

                if (response.ok) {
                    const blob = await response.blob();
                    const excelUrl = URL.createObjectURL(blob);
                    
                    const a = document.createElement('a');
                    a.href = excelUrl;
                    a.download = 'shipment_report.xlsx';
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                    URL.revokeObjectURL(excelUrl);
                    hideModal();
                } else {
                    const error = await response.json();
                    hideModal();
                    showModal('خطأ', error.error || 'فشل في توليد ملف Excel. يرجى المحاولة مرة أخرى.');
                }
            } catch (error) {
                console.error("Error generating Excel:", error);
                hideModal();
                showModal('خطأ', 'حدث خطأ غير متوقع أثناء توليد الملف.');
            }
        }
        
        async function printToNewWindow(shipmentsToPrint) {
            if (!isAuthenticated) {
                showModal('خطأ', 'يجب أن تكون مسؤولًا للطباعة.');
                return;
            }
            const printWindow = window.open('', '_blank');
            if (!printWindow) {
                showModal('خطأ', 'تم حظر النوافذ المنبثقة. يرجى السماح بها لإجراء الطباعة.');
                return;
            }
            
            try {
                const url = '/api/shipments/generate_a4_print_html';
                const response = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ shipments: shipmentsToPrint })
                });
                
                if (response.ok) {
                    const htmlContent = await response.text();
                    printWindow.document.open();
                    printWindow.document.write(htmlContent);
                    printWindow.document.close();
                    printWindow.onload = () => {
                        printWindow.print();
                    };
                } else {
                    const error = await response.json();
                    showModal('خطأ', error.error || 'فشل في توليد صفحة الطباعة.');
                    printWindow.close();
                }
            } catch (error) {
                console.error("Error generating print HTML:", error);
                showModal('خطأ', 'حدث خطأ غير متوقع أثناء الطباعة.');
                printWindow.close();
            }
        }
        
        function printA4ForShipment(shipmentId) {
             const shipment = allShipments.find(s => s.id === shipmentId);
             if (shipment) {
                 showPrintCopiesModal([shipment]);
             } else {
                 showModal('خطأ', 'لم يتم العثور على الشحنة.');
             }
        }
        
        async function handleAdminLogin() {
            showLoading();
            const username = document.getElementById('adminUsername').value;
            const password = document.getElementById('adminPassword').value;
            
            try {
                const response = await fetch('/api/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password })
                });
                const data = await response.json();
                
                if (data.success) {
                    isAuthenticated = true;
                    document.getElementById('adminLoginSection').classList.add('hidden');
                    document.getElementById('adminPanelContent').classList.remove('hidden');
                    document.getElementById('logoutButton').classList.remove('hidden');
                    document.getElementById('adminButton').classList.add('hidden');
                    showAdminTab('addShipment');
                } else {
                    showModal('فشل', 'اسم المستخدم أو كلمة المرور غير صحيح.');
                }
            } catch (error) {
                console.error('Error during login:', error);
                showModal('خطأ', 'حدث خطأ أثناء الاتصال بالخادم.');
            } finally {
                hideLoading();
            }
        }
        
        async function viewShipmentDetails(id) {
            if (!isAuthenticated) {
                showModal('خطأ', 'يجب أن تكون مسؤولًا لعرض التفاصيل.');
                return;
            }
            showLoading();
            try {
                const response = await fetch(`${API_BASE_URL}/${id}`);
                if (!response.ok) {
                    showModal('خطأ', 'لم يتم العثور على الشحنة');
                    return;
                }
                const shipment = await response.json();
                
                window.currentShipmentId = id;
                
                const content = document.getElementById('shipmentDetailsContent');
                const statusHistoryHTML = shipment.statusHistory.length > 0 ? shipment.statusHistory.map(status => `
                    <div class="flex justify-between items-center p-3 bg-gray-50 rounded-lg shadow-sm">
                        <div>
                            <div class="font-semibold">${getStatusText(status.status)}</div>
                            ${status.city ? `<div class="text-sm text-gray-600">المدينة: ${status.city}</div>` : ''}
                            ${status.notes ? `<div class="text-sm text-gray-600">ملاحظات: ${status.notes}</div>` : ''}
                        </div>
                        <div class="text-sm text-gray-500">
                            ${status.date} - ${status.time}
                        </div>
                    </div>
                `).join('') : '<div class="text-center text-gray-500 p-4">لا توجد تحديثات للحالة</div>';

                content.innerHTML = `
                    <div class="grid md:grid-cols-2 gap-8">
                        <div class="space-y-6">
                            <div class="bg-brako-blue text-white p-4 rounded-lg shadow-md">
                                <h3 class="text-lg font-bold mb-2">معلومات الشحنة</h3>
                                <div class="space-y-2 text-sm">
                                    <div><strong>رقم الشحنة:</strong> ${shipment.shipmentNumber}</div>
                                    <div><strong>رقم الفاتورة:</strong> ${shipment.invoiceNumber}</div>
                                    <div><strong>كود التتبع:</strong> ${shipment.trackingCode || 'غير محدد'}</div>
                                    <div><strong>التاريخ:</strong> ${shipment.date} - ${shipment.time}</div>
                                    <div><strong>الفرع:</strong> ${shipment.branch === 'topeka' ? 'توبيكا' : 'براكو'}</div>
                                    <div><strong>نوع الشحن:</strong> ${shipment.shippingType === 'local' ? 'محلي' : 'دولي'}</div>
                                </div>
                            </div>
                            
                            <div class="bg-brako-teal text-white p-4 rounded-lg shadow-md">
                                <h3 class="text-lg font-bold mb-2">معلومات المرسل</h3>
                                <div class="space-y-2 text-sm">
                                    <div><strong>الاسم:</strong> ${shipment.sender.name}</div>
                                    <div><strong>الهاتف:</strong> ${shipment.sender.phone}</div>
                                    <div><strong>الدولة:</strong> ${shipment.sender.country}</div>
                                    <div><strong>المدينة:</strong> ${shipment.sender.city || 'غير محدد'}</div>
                                    <div><strong>العنوان:</strong> ${shipment.sender.address}</div>
                                </div>
                            </div>
                        </div>
                        
                        <div class="space-y-6">
                            <div class="bg-brako-yellow text-white p-4 rounded-lg shadow-md">
                                <h3 class="text-lg font-bold mb-2">معلومات المستلم</h3>
                                <div class="space-y-2 text-sm">
                                    <div><strong>الاسم:</strong> ${shipment.receiver.name}</div>
                                    <div><strong>الهاتف:</strong> ${shipment.receiver.phone}</div>
                                    <div><strong>الدولة:</strong> ${shipment.receiver.country}</div>
                                    <div><strong>المدينة:</strong> ${shipment.receiver.city || 'غير محدد'}</div>
                                    <div><strong>العنوان:</strong> ${shipment.receiver.address}</div>
                                </div>
                            </div>
                            
                            <div class="bg-gray-100 p-4 rounded-lg shadow-md">
                                <h3 class="text-lg font-bold mb-2 text-brako-dark">تفاصيل الطرد</h3>
                                <div class="space-y-2 text-sm text-gray-700">
                                    <div><strong>الوزن:</strong> ${shipment.weight} كغ</div>
                                    <div><strong>العدد:</strong> ${shipment.quantity}</div>
                                    <div><strong>نوع البضاعة:</strong> ${shipment.itemType}</div>
                                    <div><strong>المحتويات:</strong> ${shipment.contents}</div>
                                    <div><strong>السعر النهائي:</strong> ${shipment.finalPrice} ${shipment.currency || 'USD'}</div>
                                    <div><strong>طريقة الدفع:</strong> ${shipment.paymentMethod === 'prepaid' ? 'دفع مقدم' : 'دفع عكسي'}</div>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="mt-8 bg-white border-2 border-brako-blue rounded-lg p-6 shadow-sm">
                        <h3 class="text-xl font-bold text-brako-blue mb-4">حالة التتبع</h3>
                        <div class="space-y-3">
                            ${statusHistoryHTML}
                        </div>
                    </div>
                `;
                
                document.getElementById('printDetailsBtn').onclick = () => printA4ForShipment(shipment.id);
                document.getElementById('whatsappDetailsBtn').onclick = () => sendWhatsApp(shipment);
                document.getElementById('deleteDetailsBtn').onclick = () => confirmDelete(shipment.id);

                showSection('shipmentDetails');
            } catch (error) {
                console.error("Error viewing shipment details:", error);
                showModal('خطأ', 'حدث خطأ أثناء عرض التفاصيل.');
            } finally {
                hideLoading();
            }
        }

        function confirmDelete(id) {
            window.currentDeleteId = id;
            showModal('تأكيد الحذف', 'هل أنت متأكد من حذف هذه الشحنة؟ لا يمكن التراجع عن هذا الإجراء.', true, deleteShipment);
        }

        async function deleteShipment() {
            if (!isAuthenticated) {
                showModal('خطأ', 'يجب أن تكون مسؤولًا للحذف.');
                return;
            }
            const id = window.currentDeleteId;
            if (id === undefined) return;
            showLoading();
            try {
                const response = await fetch(`${API_BASE_URL}/${id}`, {
                    method: 'DELETE'
                });
                
                if (response.ok) {
                    showModal('نجاح', 'تم حذف الشحنة بنجاح.');
                    showSection('admin');
                    showAdminTab('shipmentsList');
                } else {
                    showModal('خطأ', 'حدث خطأ أثناء الحذف.');
                }
            } catch (error) {
                console.error("Error deleting shipment:", error);
                showModal('خطأ', 'حدث خطأ أثناء الحذف.');
            } finally {
                hideLoading();
            }
        }

        function resetForm() {
            document.getElementById('shipmentId').value = '';
            document.getElementById('formTitle').textContent = 'إضافة شحنة جديدة';
            document.getElementById('saveButton').textContent = 'حفظ الشحنة';
            
            document.querySelector('#addShipmentSection form').reset();
            document.getElementById('insuranceDetails').classList.add('hidden');
            document.getElementById('packagingDetails').classList.add('hidden');
            document.getElementById('insuranceCost').value = '';
            document.getElementById('packagingCost').value = '';
            calculateTotal();
            
            const now = new Date();
            document.getElementById('shipmentDate').value = now.toISOString().split('T')[0];
            document.getElementById('shipmentTime').value = now.toTimeString().split(' ')[0].substring(0, 5);
        }
        
        async function loadAllShipments() {
            showLoading();
            try {
                const response = await fetch(API_BASE_URL);
                if (!response.ok) {
                    showModal('خطأ', 'فشل في تحميل الشحنات.');
                    return;
                }
                allShipments = await response.json();
                displayShipments(allShipments);
                updateStatistics(allShipments);
            } catch (error) {
                console.error("Error loading shipments:", error);
                showModal('خطأ', 'حدث خطأ أثناء تحميل الشحنات.');
            } finally {
                hideLoading();
            }
        }

        function displayShipments(shipments) {
            const tableBody = document.getElementById('shipmentsTableBody');
            
            if (shipments.length === 0) {
                tableBody.innerHTML = '<tr><td colspan="11" class="text-center p-8 text-gray-500">لا توجد شحنات مسجلة</td></tr>';
                return;
            }
            
            tableBody.innerHTML = '';
            
            shipments.forEach((shipment, index) => {
                const row = document.createElement('tr');
                row.className = index % 2 === 0 ? 'bg-gray-50 hover:bg-gray-200 transition-colors' : 'bg-white hover:bg-gray-200 transition-colors';
                
                row.ondblclick = () => viewShipmentDetails(shipment.id);

                const amountText = shipment.paymentMethod === 'cod' ? `${shipment.finalPrice} ${shipment.currency || 'USD'}` : '---';
                
                row.innerHTML = `
                    <td class="border border-gray-300 p-3">
                        <input type="checkbox" class="export-checkbox w-4 h-4 text-brako-blue rounded-md" data-id="${shipment.id}">
                    </td>
                    <td class="border border-gray-300 p-3">${shipment.shipmentNumber}</td>
                    <td class="border border-gray-300 p-3">${shipment.trackingCode || 'غير محدد'}</td>
                    <td class="border border-gray-300 p-3">${shipment.sender.name}</td>
                    <td class="border border-gray-300 p-3">${shipment.receiver.name}</td>
                    <td class="border border-gray-300 p-3">${shipment.receiver.phone}</td>
                    <td class="border border-gray-300 p-3">${shipment.quantity}</td>
                    <td class="border border-gray-300 p-3">${shipment.weight} كغ</td>
                    <td class="border border-gray-300 p-3">${amountText}</td>
                    <td class="border border-gray-300 p-3">
                        <span class="px-2 py-1 rounded-full text-xs font-semibold ${getStatusColor(shipment.status)}">
                            ${getStatusText(shipment.status)}
                        </span>
                    </td>
                    <td class="border border-gray-300 p-3 flex flex-wrap gap-2 justify-center">
                        <button onclick="viewShipmentDetails(${shipment.id})" class="bg-brako-teal text-white px-3 py-1 rounded-full text-sm hover:bg-teal-700 transition-colors">عرض</button>
                        <button onclick="startEditShipment(${shipment.id})" class="bg-brako-yellow text-brako-dark px-3 py-1 rounded-full text-sm hover:bg-yellow-300 transition-colors">تعديل</button>
                        <button onclick="sendWhatsAppForShipment(${shipment.id})" class="bg-green-500 text-white px-3 py-1 rounded-full text-sm hover:bg-green-600 transition-colors">📱</button>
                        <button onclick="printA4ForShipment(${shipment.id})" class="bg-brako-blue text-white px-3 py-1 rounded-full text-sm hover:bg-blue-700 transition-colors">🖨️</button>
                        <button onclick="confirmDelete(${shipment.id})" class="bg-red-500 text-white px-3 py-1 rounded-full text-sm hover:bg-red-700 transition-colors">حذف</button>
                    </td>
                `;
                
                tableBody.appendChild(row);
            });
        }
        
        function getStatusColor(status) {
            const colors = {
                'received': 'bg-blue-100 text-blue-800',
                'in_sorting': 'bg-indigo-100 text-indigo-800',
                'local_shipping': 'bg-purple-100 text-purple-800',
                'departed': 'bg-yellow-100 text-yellow-800',
                'at_border': 'bg-orange-100 text-orange-800',
                'in_transit': 'bg-purple-100 text-purple-800',
                'arrived_city': 'bg-teal-100 text-teal-800',
                'delayed': 'bg-red-100 text-red-800',
                'ready_pickup': 'bg-green-100 text-green-800',
                'returned': 'bg-gray-300 text-gray-800'
            };
            return colors[status] || 'bg-gray-100 text-gray-800';
        }

        function updateStatistics(shipments) {
            const totalShipments = shipments.length;
            const deliveredShipments = shipments.filter(s => s.status === 'ready_pickup').length;
            const pendingShipments = totalShipments - deliveredShipments;
            
            let totalRevenue = 0;
            shipments.forEach(shipment => {
                const price = parseFloat(shipment.finalPrice) || 0;
                totalRevenue += price;
            });
            
            document.getElementById('totalShipments').textContent = totalShipments;
            document.getElementById('totalRevenue').textContent = totalRevenue.toFixed(2);
            document.getElementById('deliveredShipments').textContent = deliveredShipments;
            document.getElementById('pendingShipments').textContent = pendingShipments;
        }

        document.addEventListener('DOMContentLoaded', async function() {
            const now = new Date();
            document.getElementById('shipmentDate').value = now.toISOString().split('T')[0];
            document.getElementById('shipmentTime').value = now.toTimeString().split(' ')[0].substring(0, 5);

            const hash = window.location.hash;
            if (hash.startsWith('#tracking/')) {
                const trackingCodeFromUrl = hash.substring(hash.indexOf('/') + 1);
                showSection('customerTracking');
                document.getElementById('trackingCodeInput').value = trackingCodeFromUrl;
                trackShipment(trackingCodeFromUrl);
            } else {
                showSection('home');
            }
        });
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    setup_database()
    app.run(debug=True)