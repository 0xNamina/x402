"""
X402 Token Scanner Bot - HYBRID VERSION (Real Scanning)
Scrapes x402scan + DexScreener for real opportunities
"""

import asyncio
import aiohttp
import os
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
from datetime import datetime, timedelta
import logging
import re
from bs4 import BeautifulSoup
import json

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===== CONFIG =====
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
BASESCAN_API_KEY = os.getenv("BASESCAN_API_KEY", "")

# URLs
X402SCAN_URL = "https://x402scan.com"
DEXSCREENER_API = "https://api.dexscreener.com/latest/dex"

# Tracking
bot_started = False
scanned_tokens = set()
last_scan_time = {}

# ===== SECURITY CHECKS =====
async def check_honeypot(session, contract_address):
    """Check honeypot via Honeypot.is API"""
    try:
        url = "https://api.honeypot.is/v2/IsHoneypot"
        params = {"address": contract_address, "chainID": "8453"}
        
        async with session.get(url, params=params, timeout=15) as response:
            if response.status != 200:
                return None, "⚠️ API error"
            
            data = await response.json()
            is_honeypot = data.get("honeypotResult", {}).get("isHoneypot", False)
            buy_tax = data.get("simulationResult", {}).get("buyTax", 0)
            sell_tax = data.get("simulationResult", {}).get("sellTax", 0)
            
            if is_honeypot:
                return False, "🚨 HONEYPOT!"
            if buy_tax > 10 or sell_tax > 10:
                return False, f"⚠️ High Tax: {buy_tax}/{sell_tax}%"
            
            return True, f"✅ Tax: {buy_tax:.1f}/{sell_tax:.1f}%"
    except Exception as e:
        logger.error(f"Honeypot check error: {e}")
        return None, "⚠️ Check timeout"

async def check_liquidity_dex(session, contract_address):
    """Check liquidity via DexScreener"""
    try:
        url = f"{DEXSCREENER_API}/tokens/{contract_address}"
        async with session.get(url, timeout=10) as response:
            if response.status != 200:
                return None, "⚠️ No data"
            
            data = await response.json()
            pairs = [p for p in data.get("pairs", []) if p.get("chainId") == "base"]
            
            if not pairs:
                return False, "❌ No Base pool"
            
            main_pair = max(pairs, key=lambda x: float(x.get("liquidity", {}).get("usd", 0)))
            liq_usd = float(main_pair.get("liquidity", {}).get("usd", 0))
            
            if liq_usd < 5000:
                return False, f"⚠️ Low liq: ${liq_usd:,.0f}"
            return True, f"✅ Liq: ${liq_usd:,.0f}"
    except Exception as e:
        logger.error(f"Liquidity check error: {e}")
        return None, "⚠️ Check failed"

async def get_token_info_dex(session, contract_address):
    """Get detailed token info from DexScreener"""
    try:
        url = f"{DEXSCREENER_API}/tokens/{contract_address}"
        async with session.get(url, timeout=10) as response:
            if response.status != 200:
                return None
            
            data = await response.json()
            pairs = [p for p in data.get("pairs", []) if p.get("chainId") == "base"]
            
            if not pairs:
                return None
            
            # Get main pair (highest liquidity)
            main_pair = max(pairs, key=lambda x: float(x.get("liquidity", {}).get("usd", 0)))
            
            return {
                "name": main_pair.get("baseToken", {}).get("name", "Unknown"),
                "symbol": main_pair.get("baseToken", {}).get("symbol", "???"),
                "price": float(main_pair.get("priceUsd", 0)),
                "mcap": float(main_pair.get("marketCap", 0)),
                "liquidity": float(main_pair.get("liquidity", {}).get("usd", 0)),
                "volume_24h": float(main_pair.get("volume", {}).get("h24", 0)),
                "price_change_24h": float(main_pair.get("priceChange", {}).get("h24", 0)),
                "created_at": main_pair.get("pairCreatedAt", 0),
                "dex_url": main_pair.get("url", ""),
                "dex_name": main_pair.get("dexId", "Unknown")
            }
    except Exception as e:
        logger.error(f"Get token info error: {e}")
        return None

async def security_scan(contract_address):
    """Quick security scan"""
    checks = []
    passed = 0
    
    try:
        async with aiohttp.ClientSession() as session:
            # Check 1: Honeypot
            hp_safe, hp_msg = await check_honeypot(session, contract_address)
            checks.append(hp_msg)
            if hp_safe: passed += 1
            
            # Check 2: Liquidity
            liq_safe, liq_msg = await check_liquidity_dex(session, contract_address)
            checks.append(liq_msg)
            if liq_safe: passed += 1
    except Exception as e:
        logger.error(f"Security scan error: {e}")
        checks.append(f"❌ Scan error")
    
    total = len(checks)
    score = (passed / total * 100) if total > 0 else 0
    
    if score >= 75:
        level, rec = "🟢 LOW RISK", "✅ SAFE"
    elif score >= 50:
        level, rec = "🟡 MEDIUM", "⚠️ CAUTION"
    else:
        level, rec = "🔴 HIGH RISK", "🚨 AVOID"
    
    return {
        "passed": passed,
        "total": total,
        "score": score,
        "level": level,
        "rec": rec,
        "checks": checks
    }

# ===== X402SCAN SCRAPER =====
async def scrape_x402scan():
    """Scrape x402scan.com for mintable tokens"""
    mint_tokens = []
    
    try:
        async with aiohttp.ClientSession() as session:
            # Fetch x402scan homepage
            async with session.get(X402SCAN_URL, timeout=15) as response:
                if response.status != 200:
                    logger.error(f"x402scan returned {response.status}")
                    return []
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Try to find server/resource listings
                # This is a generic scraper - adjust selectors based on actual HTML
                
                # Look for contract addresses (0x...)
                contract_pattern = re.compile(r'0x[a-fA-F0-9]{40}')
                contracts = set(contract_pattern.findall(html))
                
                logger.info(f"Found {len(contracts)} potential contracts on x402scan")
                
                # For each contract found, try to get details
                for contract in list(contracts)[:5]:  # Limit to 5 to avoid overload
                    # Try to find associated info
                    # Look for common patterns like token names, prices
                    
                    # Check if it's a valid Base chain token
                    token_info = await get_token_info_dex(session, contract)
                    
                    if token_info and token_info['liquidity'] > 1000:
                        # This looks like a real token
                        mint_tokens.append({
                            "name": token_info['name'],
                            "symbol": token_info['symbol'],
                            "contract": contract,
                            "type": "mint",
                            "mint_url": f"{X402SCAN_URL}/token/{contract}",
                            "price_usdc": token_info['price'],
                            "server": "x402scan",
                            "found_on": "x402scan"
                        })
                        
                        logger.info(f"Found mintable: {token_info['name']} ({token_info['symbol']})")
                
                return mint_tokens
                
    except Exception as e:
        logger.error(f"x402scan scraping error: {e}")
        return []

# ===== DEXSCREENER SCANNER =====
async def scan_dexscreener_trending():
    """Scan DexScreener for trending Base chain tokens"""
    buy_opportunities = []
    
    try:
        async with aiohttp.ClientSession() as session:
            # Get trending pairs on Base
            url = f"{DEXSCREENER_API}/pairs/base"
            
            async with session.get(url, timeout=15) as response:
                if response.status != 200:
                    logger.error(f"DexScreener returned {response.status}")
                    return []
                
                data = await response.json()
                pairs = data.get("pairs", [])
                
                logger.info(f"Scanning {len(pairs)} Base pairs from DexScreener")
                
                now = datetime.now().timestamp() * 1000  # milliseconds
                day_ago = now - (24 * 60 * 60 * 1000)
                
                for pair in pairs[:30]:  # Check top 30 pairs
                    try:
                        mcap = float(pair.get("marketCap", 0))
                        liq = float(pair.get("liquidity", {}).get("usd", 0))
                        vol_24h = float(pair.get("volume", {}).get("h24", 0))
                        price_change = float(pair.get("priceChange", {}).get("h24", 0))
                        created_at = pair.get("pairCreatedAt", 0)
                        
                        # Filters for HIGH POTENTIAL tokens
                        is_new = created_at > day_ago  # Less than 24h old
                        is_microcap = 1000 < mcap < 500000  # $1k - $500k mcap
                        has_liquidity = liq > 10000  # >$10k liquidity
                        has_volume = vol_24h > 5000  # >$5k volume
                        is_pumping = price_change > 30  # >30% gain in 24h
                        
                        # Token qualifies if: (new OR microcap) AND has_liquidity AND (has_volume OR pumping)
                        if (is_new or is_microcap) and has_liquidity and (has_volume or is_pumping):
                            contract = pair.get("baseToken", {}).get("address", "")
                            
                            if not contract:
                                continue
                            
                            # Determine potential multiplier
                            if mcap < 50000:
                                potential = "1000-10000x 🚀🚀🚀"
                            elif mcap < 100000:
                                potential = "100-1000x 🚀🚀"
                            elif mcap < 500000:
                                potential = "10-100x 🚀"
                            else:
                                potential = "5-10x"
                            
                            # Calculate age
                            age_hours = (now - created_at) / (1000 * 60 * 60)
                            age_str = f"{age_hours:.1f}h ago" if age_hours < 24 else f"{age_hours/24:.1f}d ago"
                            
                            buy_opportunities.append({
                                "name": pair.get("baseToken", {}).get("name", "Unknown"),
                                "symbol": pair.get("baseToken", {}).get("symbol", "???"),
                                "contract": contract,
                                "type": "buy",
                                "price": float(pair.get("priceUsd", 0)),
                                "mcap": mcap,
                                "liq": liq,
                                "volume_24h": vol_24h,
                                "price_change_24h": price_change,
                                "dex_url": pair.get("url", ""),
                                "potential": potential,
                                "age": age_str,
                                "dex": pair.get("dexId", "Unknown"),
                                "is_new": is_new
                            })
                            
                            logger.info(f"Found opportunity: {pair.get('baseToken', {}).get('symbol')} - {potential}")
                    
                    except Exception as e:
                        logger.error(f"Error processing pair: {e}")
                        continue
                
                # Sort by potential (lowest mcap first)
                buy_opportunities.sort(key=lambda x: x['mcap'])
                
                return buy_opportunities[:10]  # Return top 10
                
    except Exception as e:
        logger.error(f"DexScreener scanning error: {e}")
        return []

# ===== TELEGRAM ALERTS =====
async def send_mint_alert(bot, token, security):
    """Send mint alert"""
    emoji_map = {
        "🟢 LOW RISK": "✅",
        "🟡 MEDIUM": "⚠️",
        "🔴 HIGH RISK": "🚨"
    }
    emoji = emoji_map.get(security['level'], "❓")
    
    msg = f"""
{emoji} **NEW MINT OPPORTUNITY!** {emoji}

💎 **{token['name']} (${token['symbol']})**
💰 Price: ${token.get('price_usdc', 0):.6f} USDC

🌐 **Found on:** {token.get('found_on', 'x402scan')}

🔗 **MINT HERE:**
{token['mint_url']}

📋 **Contract:**
`{token['contract']}`

🛡️ **SECURITY SCAN:**
{security['level']} | {security['passed']}/{security['total']} checks passed
{security['rec']}

"""
    
    for check in security['checks']:
        msg += f"{check}\n"
    
    msg += f"""
⚡ **Quick Links:**
📊 DexScreener: https://dexscreener.com/base/{token['contract']}
🔍 Basescan: https://basescan.org/address/{token['contract']}

⚠️ **RISK DISCLAIMER:**
High risk investment. Only use money you can afford to lose!
Always DYOR before investing.
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
    """Send buy opportunity alert"""
    
    # Emoji based on potential
    if "10000x" in token['potential']:
        fire = "🔥🔥🔥🔥"
    elif "1000x" in token['potential']:
        fire = "🔥🔥🔥"
    elif "100x" in token['potential']:
        fire = "🔥🔥"
    else:
        fire = "🔥"
    
    new_badge = " 🆕 JUST LAUNCHED!" if token.get('is_new', False) else ""
    
    msg = f"""
{fire} **HIGH POTENTIAL GEM!**{new_badge} {fire}

💎 **{token['name']} (${token['symbol']})**

📊 **STATS:**
💰 Price: ${token['price']:.8f}
📈 24h Change: {token['price_change_24h']:+.1f}%
💵 Market Cap: ${token['mcap']:,.0f}
💧 Liquidity: ${token['liq']:,.0f}
📊 Volume 24h: ${token['volume_24h']:,.0f}
⏰ Age: {token['age']}
🔄 DEX: {token['dex']}

🚀 **POTENTIAL: {token['potential']}**

🔗 **BUY NOW:**
{token['dex_url']}

📋 **Contract:**
`{token['contract']}`

🛡️ **SECURITY:**
{security['level']} | {security['rec']}
"""
    
    for check in security['checks']:
        msg += f"{check}\n"
    
    msg += f"""
⚡ **Quick Links:**
🔍 Basescan: https://basescan.org/address/{token['contract']}

⚠️ **EXTREME RISK WARNING:**
Microcap tokens are EXTREMELY volatile!
• Can go 1000x or go to $0
• High risk of rug pulls
• Only invest what you can afford to LOSE
• Always do your own research!

This is NOT financial advice!
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

# ===== MAIN SCAN LOOP =====
async def auto_scan_loop(bot):
    """Main scanning loop - REAL SCANNING"""
    global scanned_tokens, last_scan_time
    scan_number = 0
    
    logger.info("🔄 Real auto-scan loop started!")
    
    # Send initial scan message
    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text="🔍 **Scanner is now ACTIVE!**\n\nScanning:\n✅ x402scan.com for mints\n✅ DexScreener for gems\n\nYou'll get alerts soon! 🚀",
            parse_mode='Markdown'
        )
    except:
        pass
    
    while True:
        try:
            scan_number += 1
            logger.info(f"[Scan #{scan_number}] Starting real scan...")
            
            # === SCAN 1: x402scan for MINT opportunities ===
            logger.info("Scanning x402scan...")
            mint_tokens = await scrape_x402scan()
            
            for token in mint_tokens:
                token_id = f"mint_{token['contract']}"
                
                if token_id not in scanned_tokens:
                    logger.info(f"🆕 New MINT found: {token['name']}")
                    
                    # Security scan
                    security = await security_scan(token['contract'])
                    
                    # Send if score >= 50%
                    if security['score'] >= 50:
                        await send_mint_alert(bot, token, security)
                        scanned_tokens.add(token_id)
                        await asyncio.sleep(2)  # Avoid spam
                    else:
                        logger.info(f"❌ Rejected (low security): {token['name']}")
            
            # === SCAN 2: DexScreener for BUY opportunities ===
            logger.info("Scanning DexScreener...")
            buy_tokens = await scan_dexscreener_trending()
            
            for token in buy_tokens:
                token_id = f"buy_{token['contract']}"
                
                # Rate limit: only alert same token once per hour
                last_alert = last_scan_time.get(token_id, 0)
                now = datetime.now().timestamp()
                
                if now - last_alert < 3600:  # 1 hour cooldown
                    continue
                
                if token_id not in scanned_tokens or (now - last_alert) > 3600:
                    logger.info(f"🆕 New BUY opportunity: {token['name']}")
                    
                    # Security scan
                    security = await security_scan(token['contract'])
                    
                    # Send if score >= 50% (relaxed for opportunities)
                    if security['score'] >= 50:
                        await send_buy_alert(bot, token, security)
                        scanned_tokens.add(token_id)
                        last_scan_time[token_id] = now
                        await asyncio.sleep(2)  # Avoid spam
                    else:
                        logger.info(f"❌ Rejected (security): {token['name']}")
            
            # Cleanup old tracking
            if len(scanned_tokens) > 1000:
                scanned_tokens = set(list(scanned_tokens)[-500:])
            
            # Clean old timestamps
            cutoff = datetime.now().timestamp() - 86400  # 24h
            last_scan_time = {k: v for k, v in last_scan_time.items() if v > cutoff}
            
            logger.info(f"[Scan #{scan_number}] Complete. Next scan in 5 minutes...")
            logger.info(f"Tracked: {len(scanned_tokens)} tokens, Alerts today: {len(last_scan_time)}")
            
            await asyncio.sleep(300)  # 5 minutes
            
        except Exception as e:
            logger.error(f"❌ Error in scan loop: {e}")
            await asyncio.sleep(60)

# ===== BOT COMMANDS =====
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command"""
    global bot_started
    
    if not bot_started:
        bot_started = True
        
        await update.message.reply_text(
            "🚀 **X402 HYBRID SCANNER ACTIVATED!**\n\n"
            "✅ Real-time scanning: ENABLED\n"
            "✅ x402scan scraping: ACTIVE\n"
            "✅ DexScreener monitoring: ACTIVE\n"
            "✅ Security checks: ENABLED\n\n"
            "📲 **You will receive:**\n"
            "🎯 MINT alerts - From x402scan\n"
            "💎 BUY alerts - High potential gems\n\n"
            "🛡️ **Security:**\n"
            "• Honeypot detection\n"
            "• Liquidity verification\n"
            "• Tax analysis\n\n"
            "⚡ **Bot is now scanning...**\n"
            "Alerts will come when opportunities appear!\n\n"
            "Use /status to check activity 📊",
            parse_mode='Markdown'
        )
        
        logger.info("✅ Bot started by user")
    else:
        await update.message.reply_text(
            "✅ Bot already scanning 24/7!\n\nUse /status for stats.",
            parse_mode='Markdown'
        )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Status command"""
    mint_count = len([t for t in scanned_tokens if t.startswith("mint_")])
    buy_count = len([t for t in scanned_tokens if t.startswith("buy_")])
    alerts_today = len(last_scan_time)
    
    await update.message.reply_text(
        f"📊 **SCANNER STATUS**\n\n"
        f"✅ Status: **ONLINE & SCANNING**\n"
        f"⏰ Time: {datetime.now().strftime('%H:%M:%S UTC')}\n"
        f"🔍 Scan interval: 5 minutes\n\n"
        f"📈 **Stats:**\n"
        f"🎯 Mint alerts sent: {mint_count}\n"
        f"💎 Buy alerts sent: {buy_count}\n"
        f"📊 Total tracked: {len(scanned_tokens)}\n"
        f"🔔 Alerts today: {alerts_today}\n\n"
        f"🔄 Scanning sources:\n"
        f"• x402scan.com ✅\n"
        f"• DexScreener Base ✅\n\n"
        f"Bot working 24/7! 🚀",
        parse_mode='Markdown'
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detailed stats"""
    mint_count = len([t for t in scanned_tokens if t.startswith("mint_")])
    buy_count = len([t for t in scanned_tokens if t.startswith("buy_")])
    
    # Recent alerts (last 6 hours)
    cutoff = datetime.now().timestamp() - (6 * 3600)
    recent = len([v for v in last_scan_time.values() if v > cutoff])
    
    await update.message.reply_text(
        f"📈 **DETAILED STATISTICS**\n\n"
        f"**All Time:**\n"
        f"🎯 Mint opportunities: {mint_count}\n"
        f"💎 Buy opportunities: {buy_count}\n"
        f"📊 Total tokens tracked: {len(scanned_tokens)}\n\n"
        f"**Recent (6h):**\n"
        f"🔔 Alerts sent: {recent}\n\n"
        f"**Scanner Health:**\n"
        f"✅ x402scan: Online\n"
        f"✅ DexScreener: Online\n"
        f"✅ Security checks: Active\n\n"
        f"Keep monitoring! 👀",
        parse_mode='Markdown'
    )

# ===== MAIN =====
async def main():
    """Main function"""
    
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("❌ Missing environment variables!")
        return
    
    logger.info("🤖 Starting X402 HYBRID Scanner Bot...")
    
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
                "🟢 **HYBRID SCANNER ONLINE**\n\n"
                "Real scanning active!\n"
                "• x402scan scraping ✅\n"
                "• DexScreener monitoring ✅\n\n"
                "Send /start to activate alerts! 🚀"
            ),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Startup message error: {e}")
    
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
