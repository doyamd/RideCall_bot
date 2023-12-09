import asyncio
import logging
import math
import sys
from os import getenv
import types
from typing import Any, Dict
import random

from aiogram import Bot, Dispatcher, F, Router, html
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from aiogram.utils.markdown import hbold
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import (
  KeyboardButton,
  Message,
  ReplyKeyboardMarkup,
  ReplyKeyboardRemove,
  CallbackQuery
)
import redis
REDIS_CLOUD_HOST = 'localhost'
REDIS_CLOUD_PORT = 6379
REDIS_CLOUD_PASSWORD = ''

redis_conn = redis.StrictRedis(
    host=REDIS_CLOUD_HOST,
    port=REDIS_CLOUD_PORT,
    password=REDIS_CLOUD_PASSWORD,
    decode_responses=True,
  )

TOKEN = "6864413454:AAHwiaMo7gAxqJ9Mokc8Iuw52cqutUDj4bw"

logging.basicConfig(level=logging.INFO)

form_router = Router()
bot = Bot(token=TOKEN)
dp = Dispatcher()

class Form(StatesGroup):
  # User info
  name = State()
  phone = State()
  role = State()
  client_rating = State()
  driver_rating = State()

  # Ride details
  location = State()
  destination = State()

driverID = ""
userID = ""

# Test Connection
async def check_redis_connection():
  try:
    redis_conn = redis.StrictRedis(
      host=REDIS_CLOUD_HOST,
      port=REDIS_CLOUD_PORT,
      password=REDIS_CLOUD_PASSWORD,
      decode_responses=True,
    )
    redis_conn.ping()
    return True
  except redis.exceptions.ConnectionError:
    return False


async def send_start_options(message: Message):
  await message.answer(
    "Hello there, please sign up or login",
    reply_markup=ReplyKeyboardMarkup(
      keyboard=[
        [
          KeyboardButton(text="Login"),
          KeyboardButton(text="Signup"),
        ]
      ],
      resize_keyboard=True,
      one_time_keyboard=True 
    )
  )

@form_router.message(CommandStart())
async def start_message(message: Message, state: FSMContext):
  await send_start_options(message)

# Login user
@form_router.message(F.text.casefold() == "login")
async def login_user(message: Message, state: FSMContext):
  global userID

  user_id = f"user:{message.from_user.id}"
  # Establish connection to Redis

  user_info = redis_conn.hgetall(user_id)
  if not user_info:
    await message.answer('User not found. Please signup.')
    await send_start_options(message) 
  else:
    await message.answer("User Found")
    user_role = user_info.get("role")

    userID = user_id
    if user_role == "Driver":
      await driver_dashboard(message=message)
    elif user_role == "Passenger":
      await passenger_dashboard(message=message)
    else:
      await message.answer("What?")


# Register new user
@form_router.message(F.text.casefold() == "signup")
async def accept_name(message: Message, state: FSMContext):
  await state.set_state(Form.phone)
  await message.answer(
            "Hello, I'm a bot that can help you to find a ride. Please, Share your contact so that we can start.",
            reply_markup=ReplyKeyboardMarkup(
                resize_keyboard=True,
                keyboard=[
                    [
                        KeyboardButton(text="Share Contact",
                                        request_contact=True,
                                          one_time_keyboard=True )
                    ]
                ],
            ),
        )



@form_router.message(Form.phone)
async def accept_role(message: Message, state: FSMContext):
  contact = message.contact       
  await state.update_data(phone=contact.phone_number)
  await state.update_data(name=contact.first_name)
  await state.set_state(Form.role)
  await message.answer(
    "Please enter your role",
    reply_markup=ReplyKeyboardMarkup(row_width=1,
      keyboard=[
        [
          KeyboardButton(text="Passenger"),
          KeyboardButton(text="Driver"),
        ]
      ],
      resize_keyboard=True,
      one_time_keyboard=True 
    )
  )

@form_router.message(Form.role)
async def save_user_data(message: Message, state: FSMContext):
  await state.update_data(role=message.text)
  data = await state.get_data()
  user_key = f"user:{message.from_user.id}"
  success = []

  # Set each key-value pair in the Redis hash
  for key, value in data.items():
    success.append(redis_conn.hset(user_key, key, value))
  if message.text == 'Driver':
    await driver_dashboard(message)
  elif message.text == 'Passenger':
    await passenger_dashboard(message)


# User dashboards
async def driver_dashboard(message: Message):
  await message.answer(
    "Welcome to the driver dashboard\nWhat would you like to do?", 
    reply_markup=ReplyKeyboardMarkup(
      keyboard=[
        [
          KeyboardButton(text="ManageProfile"),
        ]
      ],
      resize_keyboard=True,
      one_time_keyboard=True 
    )
  )
@form_router.message(F.text.casefold() == "manageprofile")
async def manage_profile(message: Message, state: FSMContext):
  data = await state.get_data()
  await message.answer(
    f"Name: {data['name']}\nPhone: {data['phone']}\nRole: {data['role']}",
    reply_markup=ReplyKeyboardRemove()
  )
  await driver_dashboard(message)

async def passenger_dashboard(message: Message):
  build = InlineKeyboardBuilder()
  build.button(text="ManageProfile ⚙", callback_data='profile')
  build.button(text="BookRide 🚕", callback_data='book')
  build.button(text="History 📃", callback_data='history')
  build.adjust(1,1,1)
  await message.answer(
    "Welcome to the passenger dashboard\nWhat would you like to do?", 
    reply_markup = build.as_markup()
  )


@form_router.callback_query(lambda c: c.data in ['profile', 'book', 'history'])
async def client_menu_handler(callback_query: CallbackQuery,  state: FSMContext, ):
  if callback_query.data == 'profile':
    data = await state.get_data()
    await callback_query.message.answer(
      f"Name: {data['name']}\nPhone: {data['phone']}\nRole: {data['role']}",
      reply_markup=ReplyKeyboardRemove()
    )
    await passenger_dashboard(callback_query.message)
  elif callback_query.data == 'book':
    global userID
    await state.update_data(user=str(userID))
    await state.set_state(Form.location)
    await callback_query.message.answer("Share your starting location 📍",
          reply_markup=ReplyKeyboardMarkup(
          resize_keyboard=True,
          keyboard=[[KeyboardButton(text="Share Location", request_location=True)]]))

  elif callback_query.data == 'history':
    history = await get_history_from_redis()
    for key, val in history:
      
      if key == str(userID):
        await callback_query.message.answer(f"Start Location: {val['location']}\nDestination: {val['destination']}")
    await passenger_dashboard(callback_query.message)

  
@form_router.message(Form.name)
async def new_phone(message: Message, state: FSMContext):
  await state.update_data(name=message.text)
  await state.set_state(Form.phone)
  await message.answer(
    "Enter your new phone number"
  )

@form_router.message(Form.phone)
async def new_role(message: Message, state: FSMContext):
  await state.update_data(phone=message.text)
  await state.set_state(Form.role)
  await message.answer(
    "Please enter your role",
    reply_markup=ReplyKeyboardMarkup(row_width=1,
      keyboard=[
        [
          KeyboardButton(text="Passenger"),
          KeyboardButton(text="Driver"),
        ]
      ],
      resize_keyboard=True
    )
  )

@form_router.message(Form.phone)
async def update_user_info(message: Message, state: FSMContext):
  await state.update_data(role=message.text)
  data = await state.get_data()

  print(f"{data['name']}\n{data['phone']}\n{data['role']}")
  # Establish connection to Redis

  user_key = f"user:{message.from_user.id}"
  success = []

  # Set each key-value pair in the Redis hash
  for key, value in data.items():
    success.append(redis_conn.hset(user_key, key, value))

  await message.answer("Your new version of data has been saved!", reply_markup=ReplyKeyboardRemove())
  await state.clear()

# Book a ride
async def get_drivers_from_redis():

  all_users = redis_conn.keys("user:*")

  drivers = []

  for user_key in all_users:
    user_info = redis_conn.hgetall(user_key)
    if user_info.get('role') == 'Driver':
      drivers.append((user_key[5:], user_info))

  return drivers

async def get_history_from_redis():

  all_users = redis_conn.keys("history:*")
  his = []
  for user_key in all_users:
    user_info = redis_conn.hgetall(user_key)
    his.append((user_key[8:], user_info))

  return his

  
  
@form_router.message(Form.location)
async def send_alerts_to_drivers(message: Message, state: FSMContext):
  print('inside')
  await state.update_data(location=message.location)
  await state.set_state(Form.destination)
  await message.answer("Please Enter Your Destination 🎯: ", reply_markup=ReplyKeyboardRemove())

 

@form_router.message(Form.destination)
async def send_alerts_to_drivers(message: Message, state: FSMContext):

  destination = message.text
#   await state.set_data(Form.destination)
  user_key = f"history:{message.from_user.id}"
  history = []
  data = await state.get_data()
  await state.update_data(destination=message.text)
  # Set each key-value pair in the Redis hash
  for key, value in data.items():
    if key == 'destination':
      history.append(redis_conn.hset(user_key, key, v))
    if key == 'location' :
      v = str(value)
      history.append(redis_conn.hset(user_key, key, v))

  drivers = await get_drivers_from_redis()
  data = await state.get_data()
  location = data['location']
  await message.answer("Searching For Driver...🔍")
  
  for driver_id, driver in drivers:
      build = InlineKeyboardBuilder()
      build.button(text='Accept 👍', callback_data = 'accept')
      build.button(text='Reject ❌', callback_data = 'reject')
      try:
        await bot.send_message(
          driver_id,
          f"New ride request from : {location}\nTo : {destination}",
          reply_markup=build.as_markup())

      except:
        print(f"Failed to send message to user")

@form_router.callback_query(lambda c: c.data in ['accept', 'reject'])
async def option_handler(callback_query: CallbackQuery,  state: FSMContext, ):
  global driverID
  global userID
  if callback_query.data == 'accept':
      driverID = callback_query.from_user.id
      drivers = await get_drivers_from_redis()
      cur_driver = driverID
      data = state.get_data()
      if drivers:
        for driver_id, driver in drivers:
          print(driver_id, cur_driver)
          if driver_id == str(cur_driver):
            build = InlineKeyboardBuilder()
            build.button(text="Rate Client", callback_data='rateC')
            build.button(text="Main Menu", callback_data='drivemenu')
            await bot.send_message(
              driver_id,
              "Have a safe drive!",
              reply_markup=build.as_markup()
            )
            await passenger_accepted_handler()
            return 
        await bot.send_message(
          driver_id,
          "Ride has been booked. Please stay tuned for other ride opportunities.",
          reply_markup=ReplyKeyboardRemove()
        )
        await driver_dashboard(callback_query.message) 
      else:
        await callback_query.message.answer("No Drivers Found😔, Please Try in a few minute ")
  elif callback_query.data == 'reject':
    reject_driver = callback_query.from_user.id
    await bot.send_message(
            reject_driver,
            "Ride rejected.",
            reply_markup=ReplyKeyboardRemove()
          )
    await driver_dashboard(callback_query.message)

@form_router.callback_query(lambda c: c.data in ['rateC', 'drivemenu'])
async def driver_option_handler(callback_query: CallbackQuery,  state: FSMContext, ):
      if callback_query.data == 'rateC':
        await rate_client(state=state)
      elif callback_query.data == 'drivemenu':
        await driver_dashboard(callback_query.message) 
      
# passenger notification 
async def passenger_accepted_handler():
  global driverID
  global userID
  time = random.randint(10, 50)
  fee = time * 50
  build = InlineKeyboardBuilder()
  build.button(text="Rate Driver", callback_data='rate')
  build.button(text="Main Menu", callback_data='menu')
  await bot.send_message(
          userID,
          f"Driver found!!!\nTime Taken 🕔:{time}\nToatal Cost 💲 :{fee}",
          reply_markup=build.as_markup()
        )
  
  
  
  
@form_router.callback_query(lambda c: c.data in ['rate', 'menu'])
async def client_option_handler(callback_query: CallbackQuery,  state: FSMContext, ):
      if callback_query.data == 'rate':
        await rate_driver(state=state)
      elif callback_query.data == 'menu':
        await passenger_dashboard(callback_query.message) 
      

# Ratings
# Rate client
async def rate_client(state: FSMContext):
  await bot.send_message(
    driverID,
    "How was your client? 🙍‍♂️",
    reply_markup=ReplyKeyboardMarkup(
    keyboard=[
      [
        KeyboardButton(text="1"),
        KeyboardButton(text="2"),
        KeyboardButton(text="3"),
        KeyboardButton(text="4"),
        KeyboardButton(text="5"),
      ],
    ],
    resize_keyboard=True
    )
  )
  await driver_dashboard()
  
async def rate_driver(state: FSMContext):
  global userID
  await bot.send_message(
    userID,
    "How was your Driver? 🚗",
    reply_markup=ReplyKeyboardMarkup(
    keyboard=[
      [
        KeyboardButton(text="1"),
        KeyboardButton(text="2"),
        KeyboardButton(text="3"),
        KeyboardButton(text="4"),
        KeyboardButton(text="5"),
      ],
    ],
    resize_keyboard=True
    )
  )
  await passenger_dashboard()

@form_router.message(Form.client_rating)
async def calculate_client_rating(message: Message, state: FSMContext):
  await state.update_data(client_rating=message.text)

  cur_rating = int(message.text)
  await message.answer(str(cur_rating))






  
async def main():
  if await check_redis_connection():
    dp.include_router(form_router)
    print("Successfully connected")
    await dp.start_polling(bot)
  else:
    print("Failed to connect to Redis. Check your connection settings.")
    
if __name__ == '__main__':
  logging.basicConfig(level=logging.INFO, stream=sys.stdout)
  asyncio.run(main())
