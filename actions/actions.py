from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.types import DomainDict
from rasa_sdk.events import UserUtteranceReverted, EventType
from rasa_sdk.events import SlotSet
from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv(dotenv_path=".env")  # Nạp biến môi trường từ file .env ở thư mục gốc
MONGODB_URI = os.environ.get("MONGODB_URI")

# MENU = {
#     "phở bò": 50000,
#     "cơm gà": 60000,
#     "bánh mì": 30000,
#     "trà sữa": 40000,
#     "gỏi cuốn": 20000,
#     "bún chả": 55000
# }

class ActionShowMenu(Action):
    def name(self) -> Text:
        return "action_show_menu"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: DomainDict) -> List[Dict[Text, Any]]:
        try:
            client = MongoClient(MONGODB_URI)
            db = client["chatbot"]
            foods = db["foods"].find({"available": True})

            menu_items = []
            for food in foods:
                menu_items.append(f"- {food['name']}: {food['price']}₫")
            if menu_items:
                dispatcher.utter_message(text="Menu hôm nay:\n" + "\n".join(menu_items))
            else:
                dispatcher.utter_message(text="Hiện chưa có món nào trong menu.")
            client.close()
        except Exception as e:
            dispatcher.utter_message(text="Không thể kết nối tới cơ sở dữ liệu. Vui lòng thử lại sau.")
            import logging
            logging.error(f"MongoDB connection error: {e}")
        return []


class ActionAddToOrder(Action):
    def name(self) -> str:
        return "action_add_to_order"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: dict) -> list:
        import logging
        logging.debug(f"Running action_add_to_order: order_list={tracker.get_slot('order_list')}, dish={tracker.get_slot('dish')}, quantity={tracker.get_slot('quantity')}, entities={tracker.latest_message.get('entities', [])}")

        # Get latest entities first
        entities = tracker.latest_message.get("entities", [])
        latest_dish = next((e["value"] for e in entities if e["entity"] == "dish"), None)
        latest_quantity = next((e["value"] for e in entities if e["entity"] == "quantity"), None)

        # Get slots
        dish = latest_dish or tracker.get_slot("dish")
        quantity = latest_quantity or tracker.get_slot("quantity")
        order_list = tracker.get_slot("order_list") or []

        # If we have both dish and quantity
        if dish and quantity:
            try:
                quantity_val = int(quantity)
                dish_name = dish.lower()

                # Kết nối MongoDB Atlas để lấy giá món ăn động
                client = MongoClient(MONGODB_URI)
                db = client["chatbot"]
                food = db["foods"].find_one({"name": {"$regex": f"^{dish_name}$", "$options": "i"}, "available": True})
                client.close()

                if food:
                    price = food["price"]
                    order_item = {
                        "dish": food["name"],
                        "quantity": quantity_val,
                        "price": price
                    }
                    order_list.append(order_item)
                    dispatcher.utter_message(text=f"Đã thêm {quantity_val} phần {food['name']} vào đơn hàng.")
                    return [
                        SlotSet("order_list", order_list),
                        SlotSet("dish", None),
                        SlotSet("quantity", None)
                    ]
                else:
                    dispatcher.utter_message(text=f"Xin lỗi, chúng tôi không có món '{dish}'.")
                    return [SlotSet("dish", None)]
            except (ValueError, TypeError):
                dispatcher.utter_message(text=f"Số lượng '{quantity}' không hợp lệ.")
                return [SlotSet("quantity", None)]
        
        # If only dish is present
        elif dish:
            return [
                SlotSet("dish", dish),
                SlotSet("quantity", None)
            ]
        
        return []

class ActionShowOrder(Action):
    def name(self) -> str:
        return "action_show_order"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: dict) -> list:
        order_list = tracker.get_slot("order_list") or []
        if not order_list:
            dispatcher.utter_message(text="Bạn chưa đặt món nào.")
            return []

        summary = []
        total = 0
        for item in order_list:
            try:
                quantity = int(item["quantity"])
            except (ValueError, TypeError, KeyError):
                continue
            price = item["price"]
            line_total = quantity * price
            summary.append(f"- {quantity} x {item['dish']}: {line_total}₫")
            total += line_total

        summary_text = "\n".join(summary)

        # Lấy danh sách khuyến mãi động từ MongoDB
        try:
            client = MongoClient(MONGODB_URI)
            db = client["chatbot"]
            promotions = list(db["promotions"].find())
            client.close()
        except Exception as e:
            promotions = []
            import logging
            logging.error(f"MongoDB promotions error: {e}")

        # Tìm khuyến mãi phù hợp nhất
        best_promo = None
        for promo in sorted(promotions, key=lambda x: x.get("min_total", 0), reverse=True):
            if total >= promo.get("min_total", 0):
                best_promo = promo
                break

        if best_promo:
            percent = best_promo.get("discount_percent", 0)
            discount = int(total * percent / 100)
            total_after = total - discount
            desc = best_promo.get("description", f"Giảm {percent}% cho đơn hàng từ {best_promo.get('min_total', 0)}₫")
            dispatcher.utter_message(text=f"Đơn hàng của bạn:\n{summary_text}\nTổng cộng: {total}₫\n{desc} (-{discount}₫). Số tiền cần thanh toán: {total_after}₫\nBạn có muốn xác nhận không?")
        else:
            dispatcher.utter_message(text=f"Đơn hàng của bạn:\n{summary_text}\nTổng cộng: {total}₫\nBạn có muốn xác nhận không?")
        return []

class ActionExecuteOrder(Action):
    def name(self) -> Text:
        return "action_execute_order"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: DomainDict) -> List[Dict[Text, Any]]:

        order_list = tracker.get_slot("order_list") or []
        if not order_list:
            dispatcher.utter_message(text="Không có đơn hàng để xác nhận.")
            return []

        dispatcher.utter_message(text="Đơn hàng của bạn đã được xác nhận! Cảm ơn bạn!")

        return [SlotSet("order_list", []), SlotSet("dish", None), SlotSet("quantity", None), SlotSet("fallback_count", 0)]


class ActionCancelOrder(Action):
    def name(self) -> Text:
        return "action_cancel_order"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: DomainDict) -> List[Dict[Text, Any]]:

        dispatcher.utter_message(text="Đơn hàng của bạn đã được hủy.")
        return [SlotSet("order_list", []), SlotSet("dish", None), SlotSet("quantity", None), SlotSet("fallback_count", 0)]
    

class ActionDefaultFallback(Action):
    def name(self) -> str:
        return "action_default_fallback"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: dict) -> list[EventType]:
        fallback_count = tracker.get_slot("fallback_count") or 0

        if fallback_count >= 3:
            dispatcher.utter_message(text="Tôi vẫn chưa hiểu bạn. Vui lòng thử lại sau.")
            return [UserUtteranceReverted(), SlotSet("fallback_count", 0)]  # Reset fallback_count
        else:
            # Check if intent is order_food_specific with valid entities
            intent = tracker.latest_message.get("intent", {}).get("name")
            entities = tracker.latest_message.get("entities", [])
            if intent == "order_food_specific" and any(e["entity"] in ["dish", "quantity"] for e in entities):
                # Skip fallback entirely
                return []
            
            dispatcher.utter_message(text="Xin lỗi, tôi chưa hiểu ý bạn. Bạn có thể nói lại không?")
            return [SlotSet("fallback_count", fallback_count + 1)]

class ActionAskQuantity(Action):
    def name(self):
        return "action_ask_quantity"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: dict):
        dish = tracker.get_slot("dish")
        if dish:
            dispatcher.utter_message(text=f"Bạn muốn gọi bao nhiêu phần {dish}?")
        return []

class ActionRestart(Action):
    def name(self) -> Text:
        return "action_restart"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: DomainDict) -> List[Dict[Text, Any]]:
        return [SlotSet("order_list", []), SlotSet("dish", None), SlotSet("quantity", None), SlotSet("fallback_count", 0)]

class ActionYouAreWelcome(Action):
    def name(self) -> Text:
        return "utter_you_are_welcome"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: DomainDict) -> List[Dict[Text, Any]]:
        dispatcher.utter_message(text="Không có gì, rất hân hạnh được phục vụ bạn!")
        return []

class ActionAskOpeningHours(Action):
    def name(self) -> Text:
        return "utter_ask_opening_hours"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: DomainDict) -> List[Dict[Text, Any]]:
        dispatcher.utter_message(text="Nhà hàng mở cửa từ 7h sáng đến 10h tối mỗi ngày.")
        return []

class ActionAskPromotion(Action):
    def name(self) -> Text:
        return "action_ask_promotion"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: DomainDict) -> List[Dict[Text, Any]]:
        try:
            client = MongoClient(MONGODB_URI)
            db = client["chatbot"]
            promotions = list(db["promotions"].find())
            client.close()
        except Exception as e:
            promotions = []
            import logging
            logging.error(f"MongoDB promotions error: {e}")

        if promotions:
            promo_lines = []
            for promo in sorted(promotions, key=lambda x: x.get("min_total", 0)):
                percent = promo.get("discount_percent", 0)
                min_total = promo.get("min_total", 0)
                desc = promo.get("description", f"Giảm {percent}% cho đơn hàng từ {min_total}₫")
                promo_lines.append(f"- {desc}")
            promo_text = "Các chương trình khuyến mãi hiện tại:\n" + "\n".join(promo_lines)
            dispatcher.utter_message(text=promo_text)
        else:
            dispatcher.utter_message(text="Hiện tại chưa có chương trình khuyến mãi nào.")
        return []
