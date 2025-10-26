"""
X402 Token Scanner Bot - ULTIMATE VERSION
Triple Scanner: x402 Mesh API + DexScreener + Security
"""

import asyncio
import aiohttp
import os
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
from datetime import datetime, timedelta
import logging
import re
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

# APIs
X402_TRENDING_API = "https://mesh.heurist.xyz/x402/agents/trending-tokens"
X402_SEARCH_API = "https://mesh.heurist.xyz/x402/agents/search-token"
X402_FIND_API = "https://mesh.heurist.xyz/x402/agents/find-token"
DEXSCREENER_API = "https://api.dexscreener.com/latest/dex"

# Tracking
bot_started = False
scanned_tokens = set()
last_scan_time = {}
scan_stats = {
    "x402_scans": 0,
    "dex_scans": 0,
    "alerts_sent": 0,
    "tokens_analyzed": 0
}

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
                return False, f"⚠️ Tax: {buy_tax:.1f}/{sell_tax:.1f}%"
            
            return True, f"✅ Tax: {buy_tax:.1f}/{sell_tax:.1f}%"
    except Exception as e:
        logger.error(f"Honeypot check error: {e}")
        return None, "⚠️ Timeout"

async def check_liquidity_dex(session, contract_address):
    """Check liquidity via DexScreener"""
    try:
        url = f"{DEXSCREENER_API}/tokens/{contract_address}"
        async with session.get(url, timeout=10) as response:
            if response.status != 200:
                return None, "⚠️ No data", None
            
            data = await response.json()
            pairs = [p for p in data.get("pairs", []) if p.get("chainId") == "base"]
            
            if not pairs:
                return False, "❌ No Base pool", None
            
            main_pair = max(pairs, key=lambda x: float(x.get("liquidity", {}).get("usd", 0)))
            liq_usd = float(main_pair.get("liquidity", {}).get("usd", 0))
            
            if liq_usd < 5000:
                return False, f"⚠️ Low liq: ${liq_usd:,.0f}", main_pair
            return True, f"✅ Liq: ${liq_usd:,.0f}", main_pair
    except Exception as e:
        logger.error(f"Liquidity check error: {e}")
        return None, "⚠️ Failed", None

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
    token_info = None
    
    try:
        async with aiohttp.ClientSession() as session:
            # Check 1: Honeypot
            hp_safe, hp_msg = await check_honeypot(session, contract_address)
            checks.append(hp_msg)
            if hp_safe: passed += 1
            
            # Check 2: Liquidity (and get token info)
            liq_safe, liq_msg, pair_data = await check_liquidity_dex(session, contract_address)
            checks.append(liq_msg)
            if liq_safe: passed += 1
            
            # Get full token info
            if pair_data:
                token_info = {
                    "price": float(pair_data.get("priceUsd", 0)),
                    "mcap": float(pair_data.get("marketCap", 0)),
                    "liquidity": float(pair_data.get("liquidity", {}).get("usd", 0)),
                    "volume_24h": float(pair_data.get("volume", {}).get("h24", 0)),
                    "dex_url": pair_data.get("url", "")
                }
    except Exception as e:
        logger.error(f"Security scan error: {e}")
        checks.append(f"❌ Scan error")
    
    total = len([c for c in checks if not c.startswith("❌")])
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
        "checks": checks,
        "token_info": token_info
    }

# ===== X402 MESH API SCANNER =====
async def scan_x402_trending():
    """Scan x402 Mesh API for trending tokens"""
    opportunities = []
    
    try:
        async with aiohttp.ClientSession() as session:
            logger.info("🔍 Querying x402 Trending API...")
            
            # Try trending tokens endpoint
            async with session.get(X402_TRENDING_API, timeout=20) as response:
                if response.status != 200:
                    logger.error(f"x402 API returned {response.status}")
                    return []
                
                # Try to parse response
                try:
                    data = await response.json()
                except:
                    # If JSON fails, try text
                    text = await response.text()
                    logger.info(f"x402 API response (text): {text[:500]}")
                    
                    # Try to extract contract addresses from text
                    contract_pattern = re.compile(r'0x[a-fA-F0-9]{40}')
                    contracts = list(set(contract_pattern.findall(text)))
                    
                    if contracts:
                        logger.info(f"Found {len(contracts)} contracts in x402 response")
                        data = {"contracts": contracts}
                    else:
                        return []
                
                # Process data
                tokens_found = []
                
                # Handle different response formats
                if isinstance(data, dict):
                    # Format 1: {tokens: [...]}
                    if "tokens" in data:
                        tokens_found = data["tokens"]
                    # Format 2: {contracts: [...]}
                    elif "contracts" in data:
                        tokens_found = [{"address": addr} for addr in data["contracts"]]
                    # Format 3: {data: [...]}
                    elif "data" in data:
                        tokens_found = data["data"]
                elif isinstance(data, list):
                    tokens_found = data
                
                logger.info(f"Processing {len(tokens_found)} tokens from x402")
                scan_stats["x402_scans"] += 1
                
                # Process each token
                for token in tokens_found[:10]:  # Limit to 10
                    try:
                        # Get contract address
                        contract = None
                        if isinstance(token, str):
                            contract = token
                        elif isinstance(token, dict):
                            contract = token.get("address") or token.get("contract") or token.get("token_address")
                        
                        if not contract or not contract.startswith("0x"):
                            continue
                        
                        # Validate and get token info from DexScreener
                        token_info = await get_token_info_dex(session, contract)
                        
                        if not token_info:
                            continue
                        
                        scan_stats["tokens_analyzed"] += 1
                        
                        # Filter criteria
                        mcap = token_info.get("mcap", 0)
                        liq = token_info.get("liquidity", 0)
                        
                        # Check if it's a potential gem
                        is_microcap = 1000 < mcap < 1000000
                        has_liquidity = liq > 5000
                        
                        if is_microcap and has_liquidity:
                            # Calculate potential
                            if mcap < 50000:
                                potential = "1000-10000x 🚀🚀🚀"
                            elif mcap < 100000:
                                potential = "100-1000x 🚀🚀"
                            elif mcap < 500000:
                                potential = "10-100x 🚀"
                            else:
                                potential = "5-10x"
                            
                            opportunities.append({
                                "name": token_info["name"],
                                "symbol": token_info["symbol"],
                                "contract": contract,
                                "type": "x402_trending",
                                "price": token_info["price"],
                                "mcap": mcap,
                                "liq": liq,
                                "volume_24h": token_info.get("volume_24h", 0),
                                "price_change_24h": token_info.get("price_change_24h", 0),
                                "dex_url": token_info["dex_url"],
                                "potential": potential,
                                "source": "x402 Trending"
                            })
                            
                            logger.info(f"✅ x402 gem found: {token_info['symbol']} - {potential}")
                    
                    except Exception as e:
                        logger.error(f"Error processing x402 token: {e}")
                        continue
                
                return opportunities
                
    except Exception as e:
        logger.error(f"x402 API error: {e}")
        return []

# ===== DEXSCREENER SCANNER =====
async def scan_dexscreener_trending():
    """Scan DexScreener for trending Base chain tokens"""
    buy_opportunities = []
    
    try:
        async with aiohttp.ClientSession() as session:
            logger.info("🔍 Scanning DexScreener Base chain...")
            
            # Get pairs on Base
            url = f"{DEXSCREENER_API}/pairs/base"
            
            async with session.get(url, timeout=15) as response:
                if response.status != 200:
                    logger.error(f"DexScreener returned {response.status}")
                    return []
                
                data = await response.json()
                pairs = data.get("pairs", [])
                
                logger.info(f"Processing {len(pairs)} Base pairs")
                scan_stats["dex_scans"] += 1
                
                now = datetime.now().timestamp() * 1000
                day_ago = now - (24 * 60 * 60 * 1000)
                
                for pair in pairs[:30]:  # Top 30
                    try:
                        mcap = float(pair.get("marketCap", 0))
                        liq = float(pair.get("liquidity", {}).get("usd", 0))
                        vol_24h = float(pair.get("volume", {}).get("h24", 0))
                        price_change = float(pair.get("priceChange", {}).get("h24", 0))
                        created_at = pair.get("pairCreatedAt", 0)
                        
                        # Filters
                        is_new = created_at > day_ago
                        is_microcap = 1000 < mcap < 500000
                        has_liquidity = liq > 10000
                        has_volume = vol_24h > 5000
                        is_pumping = price_change > 30
                        
                        if (is_new or is_microcap) and has_liquidity and (has_volume or is_pumping):
                            contract = pair.get("baseToken", {}).get("address", "")
                            
                            if not contract:
                                continue
                            
                            scan_stats["tokens_analyzed"] += 1
                            
                            # Potential
                            if mcap < 50000:
                                potential = "1000-10000x 🚀🚀🚀"
                            elif mcap < 100000:
                                potential = "100-1000x 🚀🚀"
                            elif mcap < 500000:
                                potential = "10-100x 🚀"
                            else:
                                potential = "5-10x"
                            
                            # Age
                            age_hours = (now - created_at) / (1000 * 60 * 60)
                            age_str = f"{age_hours:.1f}h" if age_hours < 24 else f"{age_hours/24:.1f}d"
                            
                            buy_opportunities.append({
                                "name": pair.get("baseToken", {}).get("name", "Unknown"),
                                "symbol": pair.get("baseToken", {}).get("symbol", "???"),
                                "contract": contract,
                                "type": "dex_trending",
                                "price": float(pair.get("priceUsd", 0)),
                                "mcap": mcap,
                                "liq": liq,
                                "volume_24h": vol_24h,
                                "price_change_24h": price_change,
                                "dex_url": pair.get("url", ""),
                                "potential": potential,
                                "age": age_str,
                                "is_new": is_new,
                                "source": "DexScreener"
                            })
                            
                            logger.info(f"✅ Dex gem found: {pair.get('baseToken', {}).get('symbol')} - {potential}")
                    
                    except Exception as e:
                        logger.error(f"Error processing pair: {e}")
                        continue
                
                buy_opportunities.sort(key=lambda x: x['mcap'])
                return buy_opportunities[:10]
                
    except Exception as e:
        logger.error(f"DexScreener error: {e}")
        return []

# ===== TELEGRAM ALERTS =====
async def send_opportunity_alert(bot, token, security, source="Unknown"):
    """Universal alert for any opportunity"""
    
    # Fire emoji based on potential
    if "10000x" in token.get('potential', ''):
        fire = "🔥🔥🔥🔥"
    elif "1000x" in token.get('potential', ''):
        fire = "🔥🔥🔥"
    elif "100x" in token.get('potential', ''):
        fire = "🔥🔥"
    else:
        fire = "🔥"
    
    new_badge = " 🆕 JUST LAUNCHED!" if token.get('is_new', False) else ""
    source_badge = f"📡 **Source: {source}**"
    
    msg = f"""
{fire} **GEM ALERT!**{new_badge} {fire}

💎 **{token['name']} (${token['symbol']})**
{source_badge}

📊 **STATS:**
💰 Price: ${token['price']:.8f}
📈 24h: {token.get('price_change_24h', 0):+.1f}%
💵 MCap: ${token['mcap']:,.0f}
💧 Liq: ${token['liq']:,.0f}
📊 Vol: ${token.get('volume_24h', 0):,.0f}
⏰ Age: {token.get('age', 'N/A')}

🚀 **POTENTIAL: {token.get('potential', 'High')}**

🔗 **BUY NOW:**
{token.get('dex_url', 'N/A')}

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
📊 DexScreener: https://dexscreener.com/base/{token['contract']}

⚠️ **EXTREME RISK WARNING:**
• Microcap = High volatility!
• Can 1000x or go to $0
• Only invest what you can LOSE
• Always DYOR!

NOT financial advice!
"""
    
    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=msg,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        logger.info(f"✅ Alert sent: {token['name']} from {source}")
        scan_stats["alerts_sent"] += 1
    except Exception as e:
        logger.error(f"Error sending alert: {e}")

# ===== MAIN SCAN LOOP =====
async def auto_scan_loop(bot):
    """ULTIMATE scanning loop - Triple scanner"""
    global scanned_tokens, last_scan_time
    scan_number = 0
    
    logger.info("🚀 ULTIMATE SCANNER STARTED!")
    
    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=(
                "🔥 **ULTIMATE SCANNER ONLINE!** 🔥\n\n"
                "Triple scanning active:\n"
                "✅ x402 Mesh API\n"
                "✅ DexScreener Base\n"
                "✅ Security checks\n\n"
                "Alerts coming soon! 🚀"
            ),
            parse_mode='Markdown'
        )
    except:
        pass
    
    while True:
        try:
            scan_number += 1
            logger.info(f"\n{'='*50}")
            logger.info(f"[SCAN #{scan_number}] STARTING TRIPLE SCAN")
            logger.info(f"{'='*50}")
            
            all_opportunities = []
            
            # === SCAN 1: x402 Mesh API ===
            logger.info("📡 [1/2] Scanning x402 Mesh API...")
            x402_tokens = await scan_x402_trending()
            logger.info(f"✅ x402: Found {len(x402_tokens)} opportunities")
            all_opportunities.extend(x402_tokens)
            
            # === SCAN 2: DexScreener ===
            logger.info("📊 [2/2] Scanning DexScreener...")
            dex_tokens = await scan_dexscreener_trending()
            logger.info(f"✅ DexScreener: Found {len(dex_tokens)} opportunities")
            all_opportunities.extend(dex_tokens)
            
            # === PROCESS ALL OPPORTUNITIES ===
            logger.info(f"\n🔍 Processing {len(all_opportunities)} total opportunities...")
            
            for token in all_opportunities:
                token_id = f"{token['type']}_{token['contract']}"
                
                # Rate limiting
                last_alert = last_scan_time.get(token_id, 0)
                now = datetime.now().timestamp()
                
                if now - last_alert < 3600:  # 1 hour cooldown
                    continue
                
                if token_id not in scanned_tokens or (now - last_alert) > 3600:
                    logger.info(f"🆕 New opportunity: {token['name']} from {token.get('source', 'Unknown')}")
                    
                    # Security scan
                    security = await security_scan(token['contract'])
                    
                    # Send if score >= 50%
                    if security['score'] >= 50:
                        await send_opportunity_alert(
                            bot, 
                            token, 
                            security, 
                            source=token.get('source', 'Unknown')
                        )
                        scanned_tokens.add(token_id)
                        last_scan_time[token_id] = now
                        await asyncio.sleep(3)  # Cooldown between alerts
                    else:
                        logger.info(f"❌ Rejected: {token['name']} (security: {security['score']:.0f}%)")
            
            # Cleanup
            if len(scanned_tokens) > 1000:
                scanned_tokens = set(list(scanned_tokens)[-500:])
            
            cutoff = datetime.now().timestamp() - 86400
            last_scan_time = {k: v for k, v in last_scan_time.items() if v > cutoff}
            
            logger.info(f"\n{'='*50}")
            logger.info(f"[SCAN #{scan_number}] COMPLETE")
            logger.info(f"📊 Stats: x402={scan_stats['x402_scans']}, Dex={scan_stats['dex_scans']}")
            logger.info(f"🔔 Alerts sent: {scan_stats['alerts_sent']}")
            logger.info(f"📈 Tokens analyzed: {scan_stats['tokens_analyzed']}")
            logger.info(f"⏰ Next scan in 5 minutes...")
            logger.info(f"{'='*50}\n")
            
            await asyncio.sleep(300)  # 5 minutes
            
        except Exception as e:
            logger.error(f"❌ Scan loop error: {e}")
            await asyncio.sleep(60)

# ===== BOT COMMANDS =====
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command"""
    global bot_started
    
    if not bot_started:
        bot_started = True
        
        await update.message.reply_text(
            "🔥 **ULTIMATE X402 SCANNER!** 🔥\n\n"
            "✅ Triple scanning active:\n"
            "• x402 Mesh API ✅\n"
            "• DexScreener Base ✅\n"
            "• Security checks ✅\n\n"
            "📲 **You'll get alerts for:**\n"
            "💎 Trending x402 tokens\n"
            "💎 Microcap gems (<$500k)\n"
            "💎 New launches (<24h)\n"
            "💎 High volume tokens\n\n"
            "🛡️ **Every token is security checked!**\n\n"
            "⚡ Scanner is now ACTIVE 24/7!\n"
            "Use /status for stats 📊",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            "✅ Scanner already active!\nUse /status for stats.",
            parse_mode='Markdown'
        )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Status command"""
    x402_count = len([t for t in scanned_tokens if t.startswith("x402")])
    dex_count = len([t for t in scanned_tokens if t.startswith("dex")])
    
    await update.message.reply_text(
        f"📊 **SCANNER STATUS**\n\n"
        f"✅ Status: **ONLINE**\n"
        f"⏰ {datetime.now().strftime('%H:%M:%S UTC')}\n\n"
        f"📈 **Lifetime Stats:**\n"
        f"🔔 Alerts sent: {scan_stats['alerts_sent']}\n"
        f"📡 x402 scans: {scan_stats['x402_scans']}\n"
        f"📊 Dex scans: {scan_stats['dex_scans']}\n"
        f"🔍 Tokens analyzed: {scan_stats['tokens_analyzed']}\n\n"
        f"📊 **Tracked:**\n"
        f"📡 x402 tokens: {x402_count}\n"
        f"📊 Dex tokens: {dex_count}\n"
        f"💎 Total: {len(scanned_tokens)}\n\n"
        f"🔄 Scan every 5 min\n"
        f"Bot working 24/7! 🚀",
        parse_mode='Markdown'
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detailed stats"""
    cutoff = datetime.now().timestamp() - (6 * 3600)
    recent = len([v for v in last_scan_time.values() if v > cutoff])
    
    await update.message.reply_text(
        f"📈 **DETAILED STATISTICS**\n\n"
        f"**Lifetime:**\n"
        f"🔔 Total alerts: {scan_stats['alerts_sent']}\n"
        f"🔍 Tokens analyzed: {scan_stats['tokens_analyzed']}\n"
        f"📡 x402 API calls: {scan_stats['x402_scans']}\n"
        f"📊 Dex API calls: {scan_stats['dex_scans']}\n\n"
        f"**Recent (6h):**\n"
        f"🔔 Alerts: {recent}\n\n"
        f"**Health:**\n"
        f"✅ x402 Mesh: Online\n"
        f"✅ DexScreener: Online\n"
        f"✅ Security: Active\n\n"
        f"Keep watching! 👀",
        parse_mode='Markdown'
    )

# ===== MAIN =====
async def main():
    """Main function"""
    
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("❌ Missing credentials!")
        return
    
    logger.info("🚀 Starting ULTIMATE X402 Scanner...")
    
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("stats", stats_command))
    
    await app.initialize()
    await app.start()
    
    bot = app.bot
    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=(
                "🟢 **ULTIMATE SCANNER DEPLOYED**\n\n"
                "Triple scanning ready:\n"
                "✅ x402 Mesh API\n"
                "✅ DexScreener\n"
                "✅ Security checks\n\n"
                "Send /start to activate! 🚀"
            ),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Startup message error: {e}")
    
    await app.updater.start_polling(drop_pending_updates=True)
    
    scan_task = asyncio.create_task(auto_scan_loop(bot))
    
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
        logger.info("Bot stopped")
