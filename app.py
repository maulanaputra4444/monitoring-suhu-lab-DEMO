import streamlit as st
import boto3
import pandas as pd
import plotly.express as px
from boto3.dynamodb.conditions import Key
from streamlit_autorefresh import st_autorefresh
import io

# --- KONFIGURASI AWS ---
# Access Key & Secret Key (Cek di IAM User AWS)
AWS_ACCESS_KEY = st.secrets["AWS_ACCESS_KEY"]
AWS_SECRET_KEY = st.secrets["AWS_SECRET_KEY"]
REGION_NAME = "us-east-1" 
TABLE_NAME = "DataSuhuLab"

def to_excel(df):
    output = io.BytesIO()

    df_export = df.copy()
    
    for col in df_export.select_dtypes(include=['datetimetz', 'datetime64[ns, Asia/Jakarta]']):
        df_export[col] = df_export[col].dt.tz_localize(None)
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_export.to_excel(writer, index=False, sheet_name='Data_Suhu')
    
    return output.getvalue()

def get_data_from_dynamodb():
    dynamodb = boto3.resource(
        'dynamodb',
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY,
        region_name=REGION_NAME
    )
    table = dynamodb.Table(TABLE_NAME)
    
    response = table.scan()
    data = response['Items']
    
    df = pd.DataFrame(data)
    
    # --- MEMBERSIHKAN DATA ---
    # Mengubah string suhu & kelembapan ke angka (float)
    df['suhu'] = df['suhu'].astype(float)
    df['kelembapan'] = df['kelembapan'].astype(float)

    df['timestamp'] = pd.to_numeric(df['timestamp'])
    
    # MENGUBAH TIMESTAMP ANEH MENJADI JAM/TANGGAL
    # unit='ms' karena data Anda dalam milidetik
    df['waktu'] = pd.to_datetime(df['timestamp'], unit='ms')
    
    # Sesuaikan ke zona waktu Jakarta (WIB)
    df['waktu'] = df['waktu'].dt.tz_localize('UTC').dt.tz_convert('Asia/Jakarta')
    
    # Urutkan berdasarkan waktu terbaru
    df = df.sort_values(by='waktu')
    return df

# --- TAMPILAN DASHBOARD STREAMLIT ---
st.set_page_config(page_title="Lab Monitoring System", layout="wide")
st.title("🌡️ Dashboard Monitoring Suhu Laboratorium")
# Dashboard akan refresh otomatis setiap 10 menit (600 detik)
# Sesuaikan dengan interval Deep Sleep Anda

st_autorefresh(interval=600 * 1000, key="datarefresh")

st.write("Data ditarik langsung dari Amazon DynamoDB")



try:
    df = get_data_from_dynamodb()

    # Tampilkan Ringkasan (Metric)
    col1, col2, col3 = st.columns(3)
    latest_data = df.iloc[-1]
    col1.metric("Suhu Saat Ini", f"{latest_data['suhu']} °C")
    col2.metric("Kelembapan", f"{latest_data['kelembapan']} %")
    col3.metric("Update Terakhir", latest_data['waktu'].strftime('%H:%M:%S'))

    # Membuat Grafik Garis
    st.subheader("Tren Suhu & Kelembapan (Real-time)")
    fig = px.line(df, x='waktu', y=['suhu', 'kelembapan'], 
                  labels={'value': 'Nilai', 'waktu': 'Jam (WIB)'},
                  title="Grafik Sensor DHT22")
    st.plotly_chart(fig, use_container_width=True)

    # Tampilkan Tabel Data
    with st.expander("Lihat Riwayat Data Lengkap"):
        st.dataframe(df[['waktu', 'suhu', 'kelembapan']].sort_values(by='waktu', ascending=False))

except Exception as e:
    st.error(f"Gagal memuat data: {e}")
    st.info("Pastikan Access Key AWS Anda benar dan tabel DynamoDB sudah ada isinya.")

    st.divider() # Garis pembatas
st.subheader("📊 Laporan & Export Data")

# Pilihan pengelompokan (Grouping)
opsi_view = st.selectbox("Kelompokkan Data Berdasarkan:", 
                         ["Data Mentah", "Rata-rata Harian", "Rata-rata Bulanan"])

df_display = df.copy()

if opsi_view == "Rata-rata Harian":
    # Kelompokkan per hari dan hitung rata-rata
    df_display = df.groupby(df['waktu'].dt.date).agg({'suhu':'mean', 'kelembapan':'mean'}).reset_index()
    df_display.columns = ['Tanggal', 'Rata-rata Suhu (°C)', 'Rata-rata Kelembapan (%)']
    
elif opsi_view == "Rata-rata Bulanan":
    # Kelompokkan per bulan
    df_display = df.groupby(df['waktu'].dt.to_period('M')).agg({'suhu':'mean', 'kelembapan':'mean'}).reset_index()
    df_display.columns = ['Bulan', 'Rata-rata Suhu (°C)', 'Rata-rata Kelembapan (%)']
    # Ubah format periode ke string agar bisa masuk Excel
    df_display[df_display.columns[0]] = df_display[df_display.columns[0]].astype(str)

# Tampilkan tabel yang sudah dikelompokkan
st.write(f"Menampilkan: {opsi_view}")
st.dataframe(df_display, use_container_width=True)

# TOMBOL DOWNLOAD EXCEL
excel_data = to_excel(df_display)
st.download_button(
    label="📥 Download Laporan ke Excel",
    data=excel_data,
    file_name=f'Laporan_Lab_{opsi_view.replace(" ", "_")}.xlsx',
    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
)