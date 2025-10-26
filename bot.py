"""
X402 Token Scanner Bot - Fully Automated Version
Langsung jalan otomatis, cukup tekan /start!
"""

import asyncio
import aiohttp
import os
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
from datetime import datetime
import logging
import json

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===== KONFIGURASI =====
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
BASESCAN_API_KEY = os.getenv("BASESCAN_API_KEY", "")

# Global state untuk tracking
bot_started = False
scanned_tokens = set()

# ===== FUNGSI KEAMANAN =====
async def check_contract_verified(session, contract_address):
    """Cek contract verification"""
    # Skip jika API key kosong
    if not BASESCAN_API_KEY or BASESCAN_API_KEY == "":
        return None, "⚠️ API key not set (skip)"
    
    try:
        url = "https://api.basescan.org/api"
        params = {
            "module": "contract",
            "action": "getsourcecode",
            "address": contract_address,
            "apikey": BASESCAN_API_KEY
        }
        async with session.get(url, params=params, timeout=10) as response:
            data = await response.json()
            if data.get("status") == "1":
                source_code = data.get("result", [{}])[0].get("SourceCode", "")
                if source_code and source_code != "":
                    return True, "✅ Contract Verified"
            return False, "⚠️ NOT Verified"
    except Exception as e:
        return None, f"⚠️ Check skipped"

async def check_honeypot(session, contract_address):
    """Cek honeypot"""
    try:
        url = "https://api.honeypot.is/v2/IsHoneypot"
        params = {"address": contract_address, "chainID": "8453"}
        
        async with session.get(url, params=params, timeout=15) as response:
            data = await response.json()
            
            is_honeypot = data.get("honeypotResult", {}).get("isHoneypot", False)
            buy_tax = data.get("simulationResult", {}).get("buyTax", 0)
            sell_tax = data.get("simulationResult", {}).get("sellTax", 0)
            
            if is_honeypot:
                return False, "🚨 HONEYPOT!"
            if buy_tax > 10 or sell_tax > 10:
                return False, f"⚠️ High Tax: {buy_tax}/{sell_tax}%"
            
            return True, f"✅ Tax: {buy_tax}/{sell_tax}%"
    except:
        return None, "⚠️ Check timeout"

async def check_liquidity(session, contract_address):
    """Cek liquidity via DexScreener"""
    try:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{contract_address}"
        async with session.get(url, timeout=10) as response:
            data = await response.json()
            pairs = [p for p in data.get("pairs", []) if p.get("chainId") == "base"]
            
            if not pairs:
                return False, "❌ No pool"
            
            liq = float(max(pairs, key=lambda x: float(x.get("liquidity", {}).get("usd", 0)))
                       .get("liquidity", {}).get("usd", 0))
            
            if liq < 10000:
                return False, f"⚠️ Low liq: ${liq:,.0f}"
            return True, f"✅ Liq: ${liq:,.0f}"
    except:
        return None, "⚠️ Check failed"

async def check_holders(session, contract_address):
    """Cek holder count"""
    # Skip jika API key kosong
    if not BASESCAN_API_KEY or BASESCAN_API_KEY == "":
        return None, "⚠️ API key not set (skip)"
    
    try:
        url = "https://api.basescan.org/api"
        params = {
            "module": "token",
            "action": "tokenholderlist",
            "contractaddress": contract_address,
            "apikey": BASESCAN_API_KEY,
            "page": 1,
            "offset": 10
        }
        async with session.get(url, params=params, timeout=10) as response:
            data = await response.json()
            holders = data.get("result", [])
            count = len(holders)
            
            if count < 5:
                return False, f"⚠️ {count} holders"
            return True, f"✅ {count}+ holders"
    except:
        return None, "⚠️ Check skipped"

async def security_scan(contract_address):
    """Full security scan"""
    checks = []
    passed = 0
    
    try:
        async with aiohttp.ClientSession() as session:
            results = await asyncio.gather(
                check_contract_verified(session, contract_address),
                check_honeypot(session, contract_address),
                check_liquidity(session, contract_address),
                check_holders(session, contract_address),
                return_exceptions=True
            )
            
            for result in results:
                if isinstance(result, Exception):
                    checks.append("⚠️ Error")
                    continue
                status, msg = result
                checks.append(msg)
                if status is True:
                    passed += 1
    except Exception as e:
        logger.error(f"Scan error: {e}")
    
    total = len([c for c in checks if not c.startswith("⚠️ Error")])
    score = (passed / total * 100) if total > 0 else 0
    
    if score >= 75:
        level = "🟢 LOW RISK"
        rec = "✅ SAFE"
    elif score >= 50:
        level = "🟡 MEDIUM"
        rec = "⚠️ CAUTION"
    else:
        level = "🔴 HIGH RISK"
        rec = "🚨 RISKY"
    
    return {
        "passed": passed,
        "total": total,
        "score": score,
        "level": level,
        "rec": rec,
        "checks": checks
    }

# ===== SCANNING X402 TOKENS =====
async def fetch_x402_tokens():
    """Fetch tokens dari x402scan - dengan scraping jika perlu"""
    try:
        async with aiohttp.ClientSession() as session:
            # Contoh: Scan x402scan.com untuk token baru
            # Karena belum ada public API, ini versi simulasi
            
            # Anda bisa tambahkan scraping logic di sini
            # atau integrate dengan API x402scan jika tersedia
            
            # DEMO: Return contoh token untuk testing
            tokens = [
                {
                    "name": "x420 Token",
                    "symbol": "x420",
                    "contract": "0x1234567890abcdef1234567890abcdef12345678",
                    "type": "mint",
                    "mint_url": "https://www.x420.dev/api/puff",
                    "price_usdc": 1,
                    "server": "x420.dev"
                }
            ]
            
            return tokens
            
    except Exception as e:
        logger.error(f"Error fetching tokens: {e}")
        return []

async def fetch_buy_opportunities():
    """Fetch token dengan potensi buy"""
    try:
        async with aiohttp.ClientSession() as session:
            # Scan DexScreener untuk token Base chain dengan potential
            url = "https://api.dexscreener.com/latest/dex/search/?q=base"
            
            async with session.get(url, timeout=10) as response:
                data = await response.json()
                pairs = data.get("pairs", [])
                
                # Filter: Base chain, liquidity >$10k, volume 24h >$5k
                candidates = []
                for pair in pairs[:20]:  # Cek 20 teratas
                    if pair.get("chainId") != "base":
                        continue
                    
                    liq = float(pair.get("liquidity", {}).get("usd", 0))
                    vol = float(pair.get("volume", {}).get("h24", 0))
                    mcap = float(pair.get("marketCap", 0))
                    
                    # Filter: liquidity >10k, volume >5k, mcap <1M (potential gem)
                    if liq > 10000 and vol > 5000 and 0 < mcap < 1000000:
                        price_change = float(pair.get("priceChange", {}).get("h24", 0))
                        
                        # Hanya yang naik >20% atau baru launch
                        if price_change > 20 or pair.get("pairCreatedAt", 0) > (datetime.now().timestamp() - 86400) * 1000:
                            candidates.append({
                                "name": pair.get("baseToken", {}).get("name", "Unknown"),
                                "symbol": pair.get("baseToken", {}).get("symbol", "???"),
                                "contract": pair.get("baseToken", {}).get("address", ""),
                                "type": "buy",
                                "price": float(pair.get("priceUsd", 0)),
                                "mcap": mcap,
                                "liq": liq,
                                "volume_24h": vol,
                                "price_change_24h": price_change,
                                "dex_url": pair.get("url", ""),
                                "potential": "100-1000x" if mcap < 100000 else "10-100x"
                            })
                
                return candidates[:5]  # Return top 5
                
    except Exception as e:
        logger.error(f"Error fetching buy opportunities: {e}")
        return []

# ===== SEND ALERTS =====
async def send_mint_alert(bot, token, security):
    """Alert untuk token mintable"""
    msg = f"""
🎯 **NEW MINT DETECTED!**

📛 **{token['name']} (${token['symbol']})**
💰 Price: ${token['price_usdc']} USDC
🌐 Server: {token.get('server', 'N/A')}

🔗 **MINT HERE:**
{token['mint_url']}

📋 Contract: `{token['contract']}`

🛡️ **SECURITY CHECK:**
{security['level']} | Score: {security['passed']}/{security['total']}
{security['rec']}

"""
    for check in security['checks']:
        msg += f"{check}\n"
    
    msg += f"""
⚠️ **DISCLAIMER:**
Auto-scan bot. NOT financial advice!
DYOR. Only invest what you can lose.

🔗 https://x402scan.com
"""
    
    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=msg,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        logger.info(f"✅ Mint alert sent: {token['name']}")
    except Exception as e:
        logger.error(f"Error sending mint alert: {e}")

async def send_buy_alert(bot, token, security):
    """Alert untuk token buy opportunity"""
    msg = f"""
💎 **HIGH POTENTIAL TOKEN!**

📛 **{token['name']} (${token['symbol']})**
💰 Price: ${token['price']:.8f}
📊 Market Cap: ${token['mcap']:,.0f}
💧 Liquidity: ${token['liq']:,.0f}
📈 24h Volume: ${token['volume_24h']:,.0f}
🚀 24h Change: +{token['price_change_24h']:.1f}%

🎯 **POTENTIAL: {token['potential']}**

🔗 **BUY HERE:**
{token['dex_url']}

📋 Contract: `{token['contract']}`

🛡️ **SECURITY CHECK:**
{security['level']} | Score: {security['passed']}/{security['total']}
{security['rec']}

"""
    for check in security['checks']:
        msg += f"{check}\n"
    
    msg += f"""
⚠️ **DISCLAIMER:**
High risk, high reward. This is NOT advice!
Microcap tokens are EXTREMELY risky.
Only use money you can afford to lose!

🔗 https://x402scan.com
"""
    
    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=msg,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        logger.info(f"✅ Buy alert sent: {token['name']}")
    except Exception as e:
        logger.error(f"Error sending buy alert: {e}")

# ===== MAIN SCANNING LOOP =====
async def auto_scan_loop(bot):
    """Loop scanning otomatis selamanya"""
    global scanned_tokens
    scan_number = 0
    
    logger.info("🔄 Auto-scan loop started!")
    
    while True:
        try:
            scan_number += 1
            logger.info(f"[Scan #{scan_number}] Checking for new tokens...")
            
            # 1. Scan mintable tokens
            mint_tokens = await fetch_x402_tokens()
            for token in mint_tokens:
                token_id = f"mint_{token['contract']}"
                
                if token_id not in scanned_tokens:
                    logger.info(f"🆕 New MINT: {token['name']}")
                    
                    # Security check
                    security = await security_scan(token['contract'])
                    
                    # Kirim jika score >= 50%
                    if security['score'] >= 50:
                        await send_mint_alert(bot, token, security)
                        scanned_tokens.add(token_id)
                    else:
                        logger.info(f"❌ Rejected (low security): {token['name']}")
            
            # 2. Scan buy opportunities  
            buy_tokens = await fetch_buy_opportunities()
            for token in buy_tokens:
                token_id = f"buy_{token['contract']}"
                
                if token_id not in scanned_tokens:
                    logger.info(f"🆕 New BUY: {token['name']}")
                    
                    # Security check
                    security = await security_scan(token['contract'])
                    
                    # Kirim jika score >= 75% (lebih strict untuk buy)
                    if security['score'] >= 75:
                        await send_buy_alert(bot, token, security)
                        scanned_tokens.add(token_id)
                    else:
                        logger.info(f"❌ Rejected (low security): {token['name']}")
            
            # Cleanup tracking (keep last 500)
            if len(scanned_tokens) > 500:
                scanned_tokens = set(list(scanned_tokens)[-500:])
            
            logger.info(f"[Scan #{scan_number}] Done. Next scan in 5 minutes...")
            await asyncio.sleep(300)  # 5 menit
            
        except Exception as e:
            logger.error(f"❌ Error in scan loop: {e}")
            await asyncio.sleep(60)  # Retry after 1 min

# ===== TELEGRAM COMMANDS =====
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command - auto start monitoring"""
    global bot_started
    
    if not bot_started:
        bot_started = True
        
        # Kirim welcome message
        await update.message.reply_text(
            "🚀 **X402 TOKEN SCANNER ACTIVATED!**\n\n"
            "✅ Auto-monitoring: ENABLED\n"
            "✅ Security checks: ACTIVE\n"
            "✅ Scan interval: 5 minutes\n\n"
            "📲 **You will receive:**\n"
            "🎯 MINT alerts - New mintable tokens\n"
            "💎 BUY alerts - High potential tokens\n\n"
            "🛡️ **Security Features:**\n"
            "• Contract verification\n"
            "• Honeypot detection\n"
            "• Liquidity check\n"
            "• Holder analysis\n\n"
            "⚡ **Bot is now scanning...**\n"
            "You'll get notified when opportunities appear!\n\n"
            "Commands:\n"
            "/status - Check bot status\n"
            "/stats - View statistics\n\n"
            "💡 Just sit back and wait for alerts! 🔔",
            parse_mode='Markdown'
        )
        
        logger.info("✅ Bot started by user")
    else:
        await update.message.reply_text(
            "✅ **Bot already running!**\n\n"
            "Monitoring is active 24/7.\n"
            "You'll receive alerts automatically.\n\n"
            "Use /status to check current status.",
            parse_mode='Markdown'
        )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Status command"""
    await update.message.reply_text(
        f"📊 **BOT STATUS**\n\n"
        f"✅ Status: **ONLINE**\n"
        f"🔄 Monitoring: **ACTIVE**\n"
        f"⏰ Time: {datetime.now().strftime('%H:%M:%S UTC')}\n"
        f"📊 Tokens tracked: {len(scanned_tokens)}\n"
        f"⚡ Scan interval: 5 minutes\n"
        f"🛡️ Security: ENABLED\n\n"
        f"Bot is working 24/7! 🚀",
        parse_mode='Markdown'
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Statistics command"""
    mint_count = len([t for t in scanned_tokens if t.startswith("mint_")])
    buy_count = len([t for t in scanned_tokens if t.startswith("buy_")])
    
    await update.message.reply_text(
        f"📈 **STATISTICS**\n\n"
        f"🎯 Mint alerts sent: {mint_count}\n"
        f"💎 Buy alerts sent: {buy_count}\n"
        f"📊 Total tracked: {len(scanned_tokens)}\n\n"
        f"Keep monitoring! 👀",
        parse_mode='Markdown'
    )

# ===== MAIN =====
async def main():
    """Main function"""
    
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("❌ Missing environment variables!")
        logger.error("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
        return
    
    logger.info("🤖 Starting X402 Auto-Scanner Bot...")
    
    # Build application
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Add handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("stats", stats_command))
    
    # Initialize
    await app.initialize()
    await app.start()
    
    # Send startup notification
    bot = app.bot
    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=(
                "🟢 **BOT ONLINE**\n\n"
                "X402 Scanner started successfully!\n"
                "Send /start to begin monitoring.\n\n"
                "Ready to scan! 🔍"
            ),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error sending startup: {e}")
    
    # Start polling
    await app.updater.start_polling(drop_pending_updates=True)
    
    # Start auto-scan loop
    scan_task = asyncio.create_task(auto_scan_loop(bot))
    
    # Keep running
    try:
        await scan_task
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        await app.stop()
        await app.shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
