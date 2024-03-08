import os
import boto3
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import LineBotApiError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, FollowEvent
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key

# 環境変数から LINE Bot のアクセストークンとシークレットを取得
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# DynamoDB テーブル名
DYNAMODB_TABLE_NAME = 'reservation_linebot'  # ステータス追跡用のテーブル

# DynamoDB リソースを取得
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(DYNAMODB_TABLE_NAME)

@handler.add(FollowEvent)
def handle_follow(event):
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text='(LINEのユーザ名)様、友達追加ありがとうございます！\n\n' +
                             '当店ではさまざまなお得なメニューやプランを提供しています。\n\n' +
                             '予約はこちらのLINEから、『予約する』と入力してください。\n\n' +
                             '予約を中断する場合は『予約をやめる』と入力してください。\n\n' +
                             'お店のメニューやプランはこちらのサイトからご確認ください(サイトのURL)。')
    )

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    user_id = event.source.user_id
    message_text = event.message.text
    user_state = get_user_state(user_id)
    reservation_information = {}
    
    asking_for_time_message = '''予約する時間帯を選択してください(番号を入力)\r\n
    1. 9:00~10:00\r\n
    2. 10:00~11:00\r\n
    3. 11:00~12:00\r\n
    4. 12:00~13:00\r\n
    5. 13:00~14:00\r\n
    6. 14:00~15:00\r\n
    7. 15:00~16:00\r\n
    8. 16:00~17:00\r\n
    9. 17:00~18:00\r\n
    10. 18:00~19:00\r\n
    11. 19:00~20:00\r\n
    12. 20:00~21:00'''
    
    asking_for_menu_message = '''予約するメニューを以下から選択してください(番号を入力)\r\n
    1. ナポリタン \r\n
    2. オムライス \r\n
    3. カルボナーラ \r\n
    4. ドリア \r\n
    5. グラタン \r\n
    6. イカ墨パスタ \r\n
    7. ほうれん草サラダ \r\n
    8. チキンプレート \r\n
    9. ハンバーグプレート \r\n
    10. ティラミス
    '''
    
    if message_text == '予約をやめる':
        reply_message(event.reply_token,'予約を中断します。再び予約を開始する際は「予約する」と入力してください')
        update_user_state(user_id,'start')
    elif message_text == '予約する' and user_state == 'start':
        reply_message(event.reply_token, '予約する人数を入力してください(1~9)')
        update_user_state(user_id, 'asking_for_people')
    elif user_state == 'asking_for_people':
        if not message_text.isdigit() or not 1 <= int(message_text) <= 9:
            reply_message(event.reply_token, '指定された数字を入力してください（1~9）。')
            return  # DynamoDBを更新せずに終了
        save_to_dynamodb(user_id, 'people', message_text)
        reply_message(event.reply_token, '予約する日付を入力してください(例：8/21)')
        update_user_state(user_id, 'asking_for_date')
    elif user_state == 'asking_for_date':
        save_to_dynamodb(user_id, 'date', message_text)
        reply_message(event.reply_token, asking_for_time_message)
        update_user_state(user_id, 'asking_for_time')
    elif user_state == 'asking_for_time':
        if not message_text.isdigit() or not 1 <= int(message_text) <= 12:
            reply_message(event.reply_token,'指定された番号を入力してください(1~12)　。')
            return
        save_to_dynamodb(user_id, 'time',message_text)
        reply_message(event.reply_token,asking_for_menu_message )
        update_user_state(user_id, 'asking_for_menu')
    elif user_state == 'asking_for_menu':
        if not message_text.isdigit() or not 1 <= int(message_text) <= 10:
            reply_message(event.reply_token, '指定された番号を入力してください（1~10）。')
            return  # DynamoDBを更新せずに終了
        save_to_dynamodb(user_id , 'menu' , message_text)
        reservation_information = get_information(user_id)
        if reservation_information:
          formatted_reservation_info = f"人数: {reservation_information.get('people', '不明')}, " \
                                       f"日付: {reservation_information.get('date', '不明')}, " \
                                       f"時間: {reservation_information.get('time', '不明')}, " \
                                       f"メニュー: {reservation_information.get('menu', '不明')}"
        else:
          formatted_reservation_info = "予約情報が見つかりませんでした。"
        confirmation_message = f'''入力ありがとうございます！\r\n
ご予約いただいた内容は\r\n
    {formatted_reservation_info}\r\n
    です\r\n
予約を確定する場合、「予約を確定する」と入力してください'''
        reply_message(event.reply_token, confirmation_message)
        update_user_state(user_id, 'confirmation')
    elif user_state == 'confirmation' and message_text == '予約を確定する':
        reply_message(event.reply_token, '予約内容を送信しました。ありがとうございます！')
        update_user_state(user_id, 'start')

def lambda_handler(event, context):
    
    

    signature = event['headers'].get('x-line-signature')
    if signature is None:
      print("x-line-signature header is missing.")
      return{
          'statusCode':400,
          'body':json.dumps('x-line-signature is not found')
      }
      
    body = event['body']
    try:
        handler.handle(body, signature)
    except LineBotApiError as e:
        print(e)

    return {
        'statusCode': 200,
        'body': json.dumps('Event processed')
    }

def get_user_state(user_id):
    response = table.get_item(Key={'user_id': user_id})
    if 'Item' in response:
        return response['Item']['state']
    else:
        return 'start'

def update_user_state(user_id, state):
    table.update_item(
        Key={'user_id': user_id},
        UpdateExpression="SET #state = :state",
        ExpressionAttributeNames={"#state": "state"},
        ExpressionAttributeValues={":state": state},
        ReturnValues="UPDATED_NEW"
    )


def save_to_dynamodb(user_id, key, value):
    table.update_item(
        Key={'user_id': user_id},
        UpdateExpression="SET #attrKey = :attrValue",
        ExpressionAttributeNames={"#attrKey": key},
        ExpressionAttributeValues={":attrValue": value},
        ReturnValues="UPDATED_NEW"
    )

def reply_message(reply_token, message):
    try:
        line_bot_api.reply_message(reply_token, TextSendMessage(text=message))
    except LineBotApiError as e:
        print(e)

def get_information(user_id):
    response = table.get_item(Key={'user_id': user_id})
    if 'Item' in response:
        return response['Item']
    else:
        return None